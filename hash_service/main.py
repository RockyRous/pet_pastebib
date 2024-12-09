import asyncio
import base64
import os
import time
import asyncpg
from fastapi import FastAPI
from redis.asyncio import Redis

app = FastAPI()

# Настройка подключения к базе данных и Redis
DB_DSN = os.getenv(
    "DATABASE_URL",  # Имя переменной окружения
    "postgres://user:password@localhost:5432/pastebin_text"  # Значение по умолчанию
)
REDIS_URL = os.getenv('REDIS_URL_HASH', default="redis://172.18.0.2/0")

REDIS_HASH_KEY = "hash_cache"
REDIS_LOCK_KEY = "hash_cache_lock"
CRITICAL_THRESHOLD = 100
BATCH_SIZE = 1000
LOCK_TIMEOUT = 10000  # 10 секунд в миллисекундах
MAX_RETRIES = 5  # Максимальное количество попыток
SEQUENCE_NAME = "my_sequence"

redis_client = Redis.from_url(REDIS_URL, decode_responses=True)


def generate_hash(seq: int) -> str:
    """ Генерация 8-значного хэша из числа """
    return base64.urlsafe_b64encode(seq.to_bytes(6, byteorder="big")).decode("utf-8")[:8]


async def retry_on_error(func, retries=MAX_RETRIES, delay=1):
    """ Повторная попытка с задержкой """
    for attempt in range(retries):
        try:
            return await func()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                raise e


async def fetch_batch_sequences(batch_size: int) -> list[int]:
    """ Получение партии сиквенсов из PostgreSQL """
    try:
        conn = await asyncpg.connect(DB_DSN)
        query = f"SELECT nextval($1) FROM generate_series(1, {batch_size})"
        result = await conn.fetch(query, SEQUENCE_NAME)
        return [row["nextval"] for row in result]
    finally:
        await conn.close()


async def acquire_lock(redis_client, lock_key, lock_timeout):
    """ блокировки Redis """
    lock_value = str(time.time())  # Уникальное значение для блокировки
    try:
        is_set = await redis_client.set(lock_key, lock_value, nx=True, px=lock_timeout)
        return is_set, lock_value
    except Exception as e:
        print(f"Error acquiring Redis lock: {e}")
        return False, None


async def release_lock(redis_client, lock_key, lock_value):
    """ Освобождение блокировки Redis """
    try:
        current_value = await redis_client.get(lock_key)
        if current_value == lock_value:
            await redis_client.delete(lock_key)  # Удаляем блокировку
    except Exception as e:
        print(f"Error releasing Redis lock: {e}")


async def populate_redis_cache():
    """ Наполнение кеша """
    lock_acquired, lock_value = await acquire_lock(redis_client, REDIS_LOCK_KEY, LOCK_TIMEOUT)
    if not lock_acquired:
        print("Failed to acquire lock for cache population.")
        return

    try:
        current_count = await redis_client.llen(REDIS_HASH_KEY)
        if current_count >= BATCH_SIZE:
            return  # Уже достаточно ключей

        sequences = await retry_on_error(lambda: fetch_batch_sequences(BATCH_SIZE))
        hashes = [generate_hash(seq) for seq in sequences]
        await retry_on_error(lambda: redis_client.lpush(REDIS_HASH_KEY, *hashes))
        print(f"Added {len(hashes)} hashes to Redis.")
    except Exception as e:
        print(f"Error populating Redis cache: {e}")
    finally:
        await release_lock(redis_client, REDIS_LOCK_KEY, lock_value)


async def ensure_redis_cache():
    """ Проверка кеша и автоматическое пополнение """
    try:
        current_count = await redis_client.llen(REDIS_HASH_KEY)
        if current_count < CRITICAL_THRESHOLD:
            await populate_redis_cache()
    except Exception as e:
        print(f"Error ensuring Redis cache: {e}")


async def ensure_redis_cache_periodically():
    """ Фоновая задача для проверки кеша с ограничением времени ожидания """
    # while True:  # Разобраться как делать
    if True:
        try:
            await asyncio.wait_for(ensure_redis_cache(), timeout=10)  # Тайм-аут 10 секунд
            await asyncio.sleep(1)
        except asyncio.TimeoutError:
            print("Timeout error occurred while ensuring Redis cache.")
        except Exception as e:
            print(f"Background cache task failed: {e}")


@app.get("/generate-hash")
async def get_hash():
    try:
        # Проверяем и пополняем кеш при необходимости
        await ensure_redis_cache()

        # Попытка извлечь из Redis
        hash_value = await redis_client.rpop(REDIS_HASH_KEY)
        if hash_value:
            return {"hash": hash_value}

        # Fallback на базу данных
        print("Redis is empty. Generating hash directly from the database.")
        sequences = await retry_on_error(lambda: fetch_batch_sequences(1))
        return {"hash": generate_hash(sequences[0])}
    except Exception as e:
        print(f"Failed to generate hash: {e}")
        return {"error": "Internal server error"}, 500


# Проверка существования последовательности и её создание, если необходимо
async def check_and_create_sequence():
    try:
        conn = await asyncpg.connect(DB_DSN)
        # Проверка, существует ли последовательность
        result = await conn.fetch(""" 
            SELECT EXISTS (
                SELECT 1 
                FROM pg_class 
                WHERE relkind = 'S' 
                  AND relname = $1
            ) AS exists;
        """, SEQUENCE_NAME)

        # Если последовательности нет, создаём её
        if not result[0]["exists"]:
            print(f"Sequence '{SEQUENCE_NAME}' does not exist. Creating it...")
            await conn.execute(f"""
                CREATE SEQUENCE {SEQUENCE_NAME}
                START WITH 1
                INCREMENT BY 1
                MINVALUE 1
                NO MAXVALUE
                CACHE 1;
            """)
            print(f"Sequence '{SEQUENCE_NAME}' created successfully.")
        else:
            print(f"Sequence '{SEQUENCE_NAME}' already exists.")
    except Exception as e:
        print(f"Error checking or creating sequence: {e}")
    finally:
        await conn.close()


@app.on_event("startup")
async def startup():
    """ Инициализация приложения """
    try:
        await check_and_create_sequence()
        print("Checked and created sequence.")

        # Redis
        await asyncio.create_task(ensure_redis_cache_periodically())
        print("Application started successfully.")
    except Exception as e:
        print(f"Failed to start application: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        if redis_client:
            await redis_client.close()
        print("Application shut down cleanly.")
    except Exception as e:
        print(f"Error during shutdown: {e}")
