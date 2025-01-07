import os
from datetime import datetime
import json
import traceback

import asyncpg
import asyncio
import redis.asyncio as redis
import pika

from logging_config import logger

### SETTINGS
DATABASE_URL_TEXT = os.getenv("DATABASE_URL_TEXT", "postgres://user:password@localhost/pastebin_text")
# Настройка RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "delayed_exchange")
credentials = pika.PlainCredentials('user', 'password')
connection_params = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)


async def create_database() -> None:
    """ Создание базы данных, если её нет. """
    # logger.debug(f"Starting database creation process. DB URL: {DATABASE_URL_TEXT}")
    try:
        conn = await asyncpg.connect(DATABASE_URL_TEXT.replace('pastebin_text', 'postgres'))
        result = await conn.fetch("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pastebin_text'")
        if not result:
            await conn.execute('CREATE DATABASE pastebin_text')
        else:
            # logger.debug("Database 'pastebin_text' already exists.")
            pass
        await conn.close()
    except Exception as e:
        logger.error(f"Error creating database: {e}")


async def ensure_redis_ready(redis_url: str, retries: int = 5, delay: int = 2):
    """ Проверка подключения к РЕДИС с ретраями. """
    # logger.debug(f"Ensuring Redis is ready at {redis_url}")
    for attempt in range(retries):
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            # logger.debug(f"Redis is available: {redis_url}")
            return redis_client
        except Exception as e:
            logger.warning(f"Try {attempt + 1}/{retries} connect to {redis_url} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    logger.error(f"Failed to connect to Redis: {redis_url}")
    raise Exception(f"Failed to connect to Redis: {redis_url}")


async def ensure_db_ready(retries: int = 5, delay: int = 2) -> None:
    """ Проверка подключения к БД с ретраями. """
    # logger.debug("Checking database readiness.")
    for attempt in range(retries):
        try:
            conn = await asyncpg.connect(DATABASE_URL_TEXT)
            await conn.close()
            # logger.debug("Database is available.")
            return
        except Exception as e:
            logger.warning(f"Try {attempt + 1}/{retries} connect to DB failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    logger.error("Failed to connect to DB.")
    raise Exception("Failed to connect to DB.")


async def create_tables() -> None:
    """ Создание таблиц в бд """
    # logger.debug("Starting table creation process.")
    conn = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                hash TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                ttl INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # logger.debug("Tables have been successfully created or already exist.")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
    finally:
        await conn.close()


async def store_in_db(short_hash: str, text: str, ttl: int) -> None:
    """ Запись поста в базу данных. """
    # logger.debug(f"Storing data in database: hash={short_hash}, ttl={ttl}")
    db = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        query = """
            INSERT INTO posts (hash, text, ttl, created_at)
            VALUES ($1, $2, $3, $4)
        """
        await db.execute(query, short_hash, text, ttl, datetime.utcnow())
        # logger.debug(f"Data stored in database for hash={short_hash}.")

        publish_message(short_hash, ttl)
    except Exception as e:
        logger.error(f"Error storing data in database: {e}")
    finally:
        await db.close()


async def get_post_db(short_hash: str) -> dict or None:
    """ Получение поста из базы данных по ключу (хэш). """
    # logger.debug(f"Fetching post from database for hash={short_hash}.")
    db = await asyncpg.connect(DATABASE_URL_TEXT)
    try:
        query = "SELECT text FROM posts WHERE hash = $1"
        result = await db.fetchrow(query, short_hash)
        return result
    except Exception as e:
        logger.error(f"Error fetching post from database: {e}")
    finally:
        await db.close()


def publish_message(hash: str, ttl: int):
    # logger.debug(f"START Publishing message to RabbitMQ: hash={hash}, ttl={ttl}")
    try:
        connection = pika.BlockingConnection(connection_params)
        channel = connection.channel()

        channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type="x-delayed-message",
            arguments={"x-delayed-type": "direct"}
        )

        message = {"hash": hash}
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="delete_key",
            body=json.dumps(message),
            properties=pika.BasicProperties(
                headers={"x-delay": ttl * 1000}
            ),
        )
        # logger.info(f"END Message published to RabbitMQ with hash={hash} and delay={ttl * 1000}ms.")
        connection.close()
    except Exception as e:
        logger.error(f"Error publishing message to RabbitMQ: {e}")
        logger.error(traceback.format_exc())
