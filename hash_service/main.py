import os
import time

import asyncio
import base64
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from prometheus_client import generate_latest, REGISTRY

from logging_config import logger, log_request
from database import fetch_batch_sequences, create_database, check_and_create_sequence


### SETTINGS
app = FastAPI()

REDIS_URL = os.getenv('REDIS_URL_HASH', default="redis://172.18.0.2/0")
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

REDIS_HASH_KEY = "hash_cache"
REDIS_LOCK_KEY = "hash_cache_lock"
CRITICAL_THRESHOLD = 100
BATCH_SIZE = 1000
LOCK_TIMEOUT = 10 * 1000  # 10 секунд в миллисекундах
MAX_RETRIES = 5  # Максимальное количество попыток


### UTILS
def generate_hash(seq: int) -> str:
    """ Генерация 8-значного хэша из числа """
    return base64.urlsafe_b64encode(seq.to_bytes(6, byteorder="big")).decode("utf-8")[:8]


async def retry_on_error(func, retries=MAX_RETRIES, delay=1):
    """ Повторная попытка с задержкой """
    # logger.debug(f'Retrying {func.__name__}')
    for attempt in range(retries):
        try:
            return await func()
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
            else:
                raise e


async def acquire_lock(redis_client, lock_key, lock_timeout):
    """ блокировки Redis """
    # logger.debug('Blocks Redis')
    lock_value = str(time.time())  # Уникальное значение для блокировки
    try:
        is_set = await redis_client.set(lock_key, lock_value, nx=True, px=lock_timeout)
        return is_set, lock_value
    except Exception as e:
        logger.error(f"Error acquiring Redis lock: {e}")
        return False, None


async def release_lock(redis_client, lock_key, lock_value) -> None:
    """ Освобождение блокировки Redis """
    # logger.debug('Releasing the Redis lock')
    try:
        current_value = await redis_client.get(lock_key)
        if current_value == lock_value:
            await redis_client.delete(lock_key)  # Удаляем блокировку
    except Exception as e:
        logger.error(f"Error releasing Redis lock: {e}")


async def populate_redis_cache() -> None:
    """ Наполнение кеша """
    # logger.debug('Populate Redis cache')
    lock_acquired, lock_value = await acquire_lock(redis_client, REDIS_LOCK_KEY, LOCK_TIMEOUT)
    if not lock_acquired:
        logger.warning("Failed to acquire lock for cache population.")
        return

    try:
        current_count = await redis_client.llen(REDIS_HASH_KEY)
        if current_count >= BATCH_SIZE:
            return  # Уже достаточно ключей

        sequences = await retry_on_error(lambda: fetch_batch_sequences(BATCH_SIZE))
        hashes = [generate_hash(seq) for seq in sequences]
        await retry_on_error(lambda: redis_client.lpush(REDIS_HASH_KEY, *hashes))
        # logger.debug(f"Added {len(hashes)} hashes to Redis.")
    except Exception as e:
        logger.error(f"Error populating Redis cache: {e}")
    finally:
        await release_lock(redis_client, REDIS_LOCK_KEY, lock_value)


async def ensure_redis_cache() -> None:
    """ Проверка кеша и автоматическое пополнение """
    # logger.debug('Cache check and automatic refill')
    try:
        current_count = await redis_client.llen(REDIS_HASH_KEY)
        if current_count < CRITICAL_THRESHOLD:
            await populate_redis_cache()
    except Exception as e:
        logger.error(f"Error ensuring Redis cache: {e}")


async def ensure_redis_cache_periodically() -> None:
    """ Фоновая задача для проверки кеша с ограничением времени ожидания """
    logger.debug('Background task for cache check with timeout limit')
    while True:
        try:
            # logger.debug('ensure_redis_cache_periodically start')  # fixme я не понимаю работает ли этот блок
            await asyncio.wait_for(ensure_redis_cache(), timeout=10)  # Тайм-аут 10 секунд
            await asyncio.sleep(60)  # Задержка в 60 секунд перед следующей проверкой # todo: Вынести параметр в енв
        except asyncio.TimeoutError:
            logger.error("Timeout error occurred while ensuring Redis cache.")
        except Exception as e:
            logger.error(f"Background cache task failed: {e}")


### ENDPOINTS
@app.on_event("startup")
async def startup() -> None:
    """ Инициализация приложения """
    # logger.debug('Startup')
    try:
        await create_database()
        logger.info("Checked and created database..")
        await check_and_create_sequence()
        logger.info("Checked and created sequence.")

        # Запуск фоновой задачи для периодической проверки кеша
        asyncio.create_task(ensure_redis_cache_periodically())  # Запуск фоновой задачи
        logger.info("Background task for cache checking started.")

        logger.info("Application started successfully.")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Request:
    """ Middleware для логирования запросов и измерения их времени. """
    # logger.debug(f"Processing request: {request.method} {request.url}")
    start_time = time.time()
    response = await call_next(request)
    response_time = time.time() - start_time

    # Логируем и добавляем метрики
    log_request(request, response_time, response.status_code)
    # logger.info(f"Request processed: {request.method} {request.url} in {response_time:.3f}s, status={response.status_code}")

    return response


@app.get("/metrics")
async def metrics() -> Response:
    """ Эндпоинт для отдачи метрик в формате, который Prometheus может собрать. """
    return Response(generate_latest(REGISTRY), media_type="text/plain")


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


@app.get("/generate-hash")
async def get_hash():
    """ Функция для получения короткой ссылки (хэша) """
    # logger.debug('get_hash start')
    try:
        # Проверяем и пополняем кеш при необходимости
        await ensure_redis_cache()

        # Попытка извлечь из Redis
        hash_value = await redis_client.rpop(REDIS_HASH_KEY)
        if hash_value:
            return {"hash": hash_value}

        # Fallback на базу данных
        logger.info("Redis is empty. Generating hash directly from the database.")
        sequences = await retry_on_error(lambda: fetch_batch_sequences(1))
        return {"hash": generate_hash(sequences[0])}
    except Exception as e:
        logger.error(f"Failed to generate hash: {e}")
        return {"error": "Internal server error"}, 500
