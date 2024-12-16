import os
from datetime import datetime
import json

import asyncpg
import asyncio
import redis.asyncio as redis
import pika

from logging_config import logger


### SETTINGS
DATABASE_URL_TEXT = os.getenv("DATABASE_URL_TEXT", "postgres://user:password@localhost/pastebin_text")
# Настройка RabbitMQ
RABBITMQ_HOST = "localhost"
EXCHANGE_NAME = "delayed_exchange"


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


async def store_in_db(short_hash: str, text: str, ttl: int):
    """ Сохраняем текст в БД """
    db = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        query = """
            INSERT INTO posts (hash, text, ttl, created_at)
            VALUES ($1, $2, $3, $4)
        """
        await db.execute(query, short_hash, text, ttl, datetime.utcnow())

        # Публикация сообщения в RabbitMQ
        publish_message(short_hash, ttl)

    finally:
        await db.close()


async def get_post_db(short_hash: str):
    """ Если текста нет в Redis, ищем его в БД """
    db = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        query = "SELECT text FROM posts WHERE hash = $1"
        result = await db.fetchrow(query, short_hash)
        return result
    finally:
        await db.close()


def get_rabbit_connection():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    return connection


def publish_message(hash: str, ttl: int):
    connection = get_rabbit_connection()
    channel = connection.channel()

    # Создание обменника с типом x-delayed-message
    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type="x-delayed-message",
        arguments={"x-delayed-type": "direct"}
    )

    # Публикация сообщения с задержкой
    message = {"hash": hash}
    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key="delete_key",
        body=json.dumps(message),
        properties=pika.BasicProperties(
            headers={"x-delay": ttl * 1000}  # Задержка в миллисекундах
        ),
    )
    connection.close()
