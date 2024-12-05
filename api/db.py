import os
import asyncpg


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

async def create_tables():
    """ Функция для создания базы данных и таблиц """
    conn = await asyncpg.connect(DATABASE_URL_TEXT)

    # Создание таблицы posts
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            hash TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            ttl INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Создание таблицы hashes с уникальным индексом
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS hashes (
            short_hash TEXT PRIMARY KEY,
            ttl INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_short_hash UNIQUE (short_hash)
        )
    """)

    print("Таблица успешно создана или уже существует.")
    await conn.close()
