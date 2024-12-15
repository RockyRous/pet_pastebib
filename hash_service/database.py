import os
import asyncpg

from logging_config import logger

### SETTINGS
DB_DSN = os.getenv("DATABASE_URL", "postgres://user:password@localhost/pastebin_hash")
SEQUENCE_NAME = "my_sequence"  # Название очереди # todo: rename


async def fetch_batch_sequences(batch_size: int) -> list[int]:
    """ Получение партии сиквенсов из PostgreSQL """
    logger.debug('Получение партии сиквенсов из PostgreSQL')
    conn = await asyncpg.connect(DB_DSN)
    try:
        query = f"SELECT nextval($1) FROM generate_series(1, {batch_size})"
        result = await conn.fetch(query, SEQUENCE_NAME)
        return [row["nextval"] for row in result]
    finally:
        await conn.close()


async def create_database():
    logger.debug(f'DB url: {DB_DSN}')
    # Подключаемся к PostgreSQL, чтобы проверить наличие базы данных
    conn = await asyncpg.connect(DB_DSN.replace('pastebin_hash', 'postgres'))
    try:
        # Создаем базу данных, если она не существует
        result = await conn.fetch("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'pastebin_hash'")
        if not result:
            await conn.execute('CREATE DATABASE pastebin_hash')
            logger.info("Database 'pastebin_hash' created.")
        await conn.close()
    except Exception as e:
        logger.error(f"Error creating database: {e}")


async def check_and_create_sequence():
    """ Проверка существования последовательности и её создание, если необходимо """
    logger.debug('Проверка существования последовательности и её создание, если необходимо')
    conn = await asyncpg.connect(DB_DSN)
    try:
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
            logger.info(f"Sequence '{SEQUENCE_NAME}' does not exist. Creating it...")
            await conn.execute(f"""
                CREATE SEQUENCE {SEQUENCE_NAME}
                START WITH 1
                INCREMENT BY 1
                MINVALUE 1
                NO MAXVALUE
                CACHE 1;
            """)
            logger.info(f"Sequence '{SEQUENCE_NAME}' created successfully.")
        else:
            logger.info(f"Sequence '{SEQUENCE_NAME}' already exists.")
    except Exception as e:
        logger.error(f"Error checking or creating sequence: {e}")
    finally:
        await conn.close()
