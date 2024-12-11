from datetime import datetime, timedelta
from os import getenv

import aiohttp
import asyncpg
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from db import create_tables, get_db, ensure_db_ready, ensure_redis_ready, DATABASE_URL_TEXT

# Настройка
app = FastAPI()

# Инициализация Redis
REDIS_URL_TEXT = getenv('REDIS_URL_TEXT', default="redis://172.18.0.3/0")
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)

HASH_SERVICE_URL = getenv('HASH_SERVICE_URL', default="http://hash-service:8002/generate-hash")

######################################## Pydantic Models
class CreatePostRequest(BaseModel):
    text: str = Field(..., max_length=500)
    ttl: int = Field(..., gt=0)


class CreatePostResponse(BaseModel):
    short_url: str


######################################## FAST API

@app.on_event("startup")
async def on_startup():
    """Инициализация при старте приложения."""
    try:
        # Убедитесь, что база данных доступна
        await ensure_db_ready()
        await create_tables()

        # Убедитесь, что Redis доступен
        global redis
        redis = await ensure_redis_ready(REDIS_URL_TEXT)
    except Exception as e:
        print(f"Ошибка при старте приложения: {e}")


async def store_in_redis_or_db(short_hash: str, text: str, ttl: int):
    """Сохранение текста в Redis (если TTL короткий) или в БД."""
    if ttl <= 3600:  # Если TTL <= 1 час
        # Сохраняем текст в Redis (redis_text)
        await redis.set(short_hash, text, ex=ttl)
    else:
        # Сохраняем текст в БД
        db = await asyncpg.connect(DATABASE_URL_TEXT)
        try:
            query = """
                INSERT INTO posts (hash, text, ttl, created_at)
                VALUES ($1, $2, $3, $4)
            """
            await db.execute(query, short_hash, text, ttl, datetime.utcnow())
        finally:
            await db.close()


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest):
    try:
        # Генерация уникального хэша

        async with aiohttp.ClientSession() as session:
            async with session.get(HASH_SERVICE_URL) as response:
                if response.status != 200:
                    raise HTTPException(status_code=response.status,
                                        detail=f"Error from hash service: {await response.text()}")
                data = await response.json()
                short_hash = data['hash']

        # Сохранение в Redis или БД
        await store_in_redis_or_db(short_hash, request.text, request.ttl)

        # Генерация короткой ссылки
        short_url = f"http://localhost:8001/{short_hash}"

        return {"short_url": short_url}
    except Exception as e:
        print(f"Ошибка в create_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/{short_hash}")
async def get_post(short_hash: str, db=Depends(get_db)):
    try:
        # Сначала пытаемся получить текст из Redis (redis_text)
        text = await redis.get(short_hash)

        if not text:
            # Если текста нет в Redis, ищем его в БД
            query = "SELECT text FROM posts WHERE hash = $1"
            result = await db.fetchrow(query, short_hash)

            if result:  # todo: Почему-то при переходе ссылкой на кеш, в логах дает 404. При юзе ендпоинта норм.
                text = result["text"]

                # Кэшируем текст в Redis (redis_text)
                await redis.set(short_hash, text, ex=600)  # TTL = 600 секунд
            else:
                raise HTTPException(status_code=404, detail="Post not found")

        return {"text": text}
    except Exception as e:
        print(f"Ошибка в get_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
