import time
from datetime import datetime
from os import getenv
import json

import aiohttp
import asyncpg
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
import pika

from database import create_tables, ensure_db_ready, ensure_redis_ready, create_database, store_in_db, get_post_db
from logging_config import log_request, logger


### SETTINGS
app = FastAPI()

REDIS_URL_TEXT = getenv('REDIS_URL_TEXT', default="redis://172.18.0.3/0")
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)

HASH_SERVICE_URL = getenv('HASH_SERVICE_URL', default="http://hash-service:8002/generate-hash")


### Pydantic Models
class CreatePostRequest(BaseModel):
    text: str = Field(..., max_length=500)
    ttl: int = Field(..., gt=0)


class CreatePostResponse(BaseModel):
    short_url: str


### UTILS
async def store_in_redis_or_db(short_hash: str, text: str, ttl: int):
    """Сохранение текста в Redis (если TTL короткий) или в БД."""
    if ttl <= 3600:  # Если TTL <= 1 час
        # Сохраняем текст в Redis (redis_text)
        await redis.set(short_hash, text, ex=ttl)
    else:
        # Сохраняем текст в БД
        await store_in_db(short_hash, text, ttl)


### ENDPOINTS
@app.on_event("startup")
async def on_startup():
    """ Инициализация при старте приложения. """
    try:
        # Убедитесь, что база данных доступна
        await create_database()
        await ensure_db_ready()
        await create_tables()

        # Убедитесь, что Redis доступен
        global redis
        redis = await ensure_redis_ready(REDIS_URL_TEXT)
    except Exception as e:
        logger.error(f"Ошибка при старте приложения: {e}")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """ Middleware для логирования запросов и измерения их времени. """
    start_time = time.time()
    response = await call_next(request)
    response_time = time.time() - start_time

    # Логируем и добавляем метрики
    log_request(request, response_time, response.status_code)

    return response


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")


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
        short_url = f"http://localhost:8001/get/{short_hash}"

        return {"short_url": short_url}
    except Exception as e:
        logger.error(f"Ошибка в create_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/get/{short_hash}")
async def get_post(short_hash: str):
    try:
        # Сначала пытаемся получить текст из Redis
        text = await redis.get(short_hash)

        if not text:
            result = await get_post_db(short_hash)

            if result:
                text = result["text"]

                # Кэшируем текст в Redis (redis_text)
                await redis.set(short_hash, text, ex=600)  # TTL = 600 секунд
            else:
                raise HTTPException(status_code=404, detail="Post not found")

        return {"text": text}
    except Exception as e:
        logger.error(f"Ошибка в get_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
