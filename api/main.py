import hashlib

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from datetime import datetime, timedelta
import os
import asyncpg


### Настройки

# Инициализация Redis
REDIS_URL_TEXT = "redis://localhost:6379/0"
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)

# Инициализация FastAPI
app = FastAPI()

# Инициализация BD
DATABASE_URL_TEXT = os.getenv(
    "DATABASE_URL",  # Имя переменной окружения
    "postgres://user:password@localhost:5432/pastebin_text"  # Значение по умолчанию
)

######################################## Pydantic Models
class CreatePostRequest(BaseModel):
    text: str = Field(..., max_length=500)
    ttl: int = Field(..., gt=0)

class CreatePostResponse(BaseModel):
    short_url: str

class GenerateHashRequest(BaseModel):
    text: str
    ttl: int

class GenerateHashResponse(BaseModel):
    short_hash: str


######################################## FAST API
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

@app.on_event("startup")
async def on_startup():
    """ Вызов функции для создания таблиц при старте приложения """
    try:
        await create_database()
        await create_tables()
    except Exception as e:
        print(f"Ошибка при подключении или создании таблиц: {e}")

def generate_unique_hash(text: str) -> str:
    """ Функция для генерации уникального хеша """
    hash_object = hashlib.md5(text.encode())
    return hash_object.hexdigest()[:8]


# Генерация хэша и проверка уникальности
async def generate_hash(request: dict, db) -> dict:
    attempt = 0
    while attempt < 5:  # Ограничиваем количество попыток
        # Генерация уникального хэша с солью (например, текущей датой)
        short_hash = generate_unique_hash(request['text'] + str(datetime.utcnow()) + str(attempt))

        # Проверка наличия хэша в БД
        query = "SELECT 1 FROM hashes WHERE short_hash = $1"
        existing_hash = await db.fetchrow(query, short_hash)

        if not existing_hash:
            # Если хэш уникален, сохраняем его
            query = """
                INSERT INTO hashes (short_hash, ttl, created_at)
                VALUES ($1, $2, $3)
            """
            await db.execute(query, short_hash, request['ttl'], datetime.utcnow())
            return {"short_hash": short_hash}

        attempt += 1

    raise HTTPException(status_code=500, detail="Unable to generate unique hash after multiple attempts")


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest, db=Depends(get_db)):
    response = await generate_hash({"text": request.text, "ttl": request.ttl}, db=db)
    short_hash = response.get("short_hash")

    # Создаем короткий URL
    short_url = f"http://localhost:8000/{short_hash}"

    # Запись в таблицу posts
    query = """
        INSERT INTO posts (hash, text, ttl, created_at)
        VALUES ($1, $2, $3, $4)
    """
    await db.execute(query, short_hash, request.text, request.ttl, datetime.utcnow())

    return {"short_url": short_url}


@app.get("/{short_hash}")
async def get_post(short_hash: str, db=Depends(get_db)):
    # Проверяем, есть ли текст в базе данных
    query = "SELECT text, ttl FROM posts WHERE hash = $1"
    post = await db.fetchrow(query, short_hash)

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Возвращаем текст поста
    return {"text": post['text']}