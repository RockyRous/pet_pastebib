import os
import asyncpg
import redis.asyncio as redis
import asyncio
from logging_config import logger

# Инициализация BD
# DATABASE_URL_TEXT = os.getenv("DATABASE_URL", "postgres://user:password@localhost:5432/pastebin_text")
DATABASE_URL_TEXT = os.getenv("DATABASE_URL", "postgres://user:password@localhost/pastebin_text")


async def get_db():
    """ Функция для получения подключения к базе данных """
    conn = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        yield conn
    finally:
        await conn.close()


async def create_database():
    logger.debug(f'DB url: {DATABASE_URL_TEXT}')
    try:
        # Подключаемся к PostgreSQL, чтобы проверить наличие базы данных
        conn = await asyncpg.connect(DATABASE_URL_TEXT.replace('pastebin_text', 'postgres'))
        # Создаем базу данных, если она не существует
        result = await conn.fetch("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pastebin_text'")
        if not result:
            await conn.execute('CREATE DATABASE pastebin_text')
            logger.info("Database 'pastebin_text' created.")
        await conn.close()
    except Exception as e:
        logger.error(f"Error creating database: {e}")


async def ensure_redis_ready(redis_url, retries=5, delay=2):
    for attempt in range(retries):
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info(f"Redis доступен: {redis_url}")
            return redis_client
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}/{retries} подключения к {redis_url} не удалась: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    raise Exception(f"Не удалось подключиться к Redis: {redis_url}")


async def ensure_db_ready(retries=5, delay=2):
    """Проверка доступности базы данных с ретри-механизмом."""
    for attempt in range(retries):
        try:
            conn = await asyncpg.connect(DATABASE_URL_TEXT)
            await conn.close()
            logger.info("База данных доступна.")
            return
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}/{retries} подключения к базе данных не удалась: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    raise Exception("Не удалось подключиться к базе данных.")


async def create_tables():
    """Создание таблиц в базе данных."""
    conn = await asyncpg.connect(DATABASE_URL_TEXT)
    logger.debug(f'DB url: {DATABASE_URL_TEXT}')
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
        logger.info("Таблицы успешно созданы или уже существуют.")
    finally:
        await conn.close()
