import os
import asyncpg
import redis.asyncio as redis
import asyncio

# Инициализация BD
DATABASE_URL_TEXT = os.getenv(
    "DATABASE_URL",  # Имя переменной окружения
    "postgres://user:password@localhost:5432/pastebin_text"  # Значение по умолчанию
)


async def get_db():
    """ Функция для получения подключения к базе данных """
    conn = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        yield conn
    finally:
        await conn.close()


async def create_database():
    try:
        # Подключаемся к PostgreSQL, чтобы проверить наличие базы данных
        conn = await asyncpg.connect(

            user="user",
            password="password",
            database="postgres",  # Подключаемся к базе данных по умолчанию
            host="localhost",
            port=5432
        )
        # Создаем базу данных, если она не существует
        result = await conn.fetch("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pastebin_text'")
        if not result:
            await conn.execute('CREATE DATABASE pastebin_text')
            print("Database 'pastebin_text' created.")
        await conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")


async def ensure_redis_ready(retries=5, delay=2):
    for attempt in range(retries):
        try:
            # Подключение с использованием redis.asyncio
            redis_client = redis.from_url("redis://redis_text:6379")
            await redis_client.ping()  # Проверка подключения
            print("Redis доступен.")
            return redis_client
        except Exception as e:
            print(f"Попытка {attempt + 1}/{retries} подключения к Redis не удалась: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    raise Exception("Не удалось подключиться к Redis.")


async def ensure_db_ready(retries=5, delay=2):
    """Проверка доступности базы данных с ретри-механизмом."""
    for attempt in range(retries):
        try:
            conn = await asyncpg.connect(DATABASE_URL_TEXT)
            await conn.close()
            print("База данных доступна.")
            return
        except Exception as e:
            print(f"Попытка {attempt + 1}/{retries} подключения к базе данных не удалась: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    raise Exception("Не удалось подключиться к базе данных.")


async def create_tables():
    """Создание таблиц в базе данных."""
    conn = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        # Создание таблицы posts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                hash TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                ttl INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Создание таблицы hashes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                short_hash TEXT PRIMARY KEY,
                ttl INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_short_hash UNIQUE (short_hash)
            )
        """)
        print("Таблицы успешно созданы или уже существуют.")
    finally:
        await conn.close()
