import time
from os import getenv

from prometheus_client import generate_latest, REGISTRY
import aiohttp
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from database import create_tables, ensure_db_ready, ensure_redis_ready, create_database, store_in_db, get_post_db
from logging_config import log_request, logger


### SETTINGS
app = FastAPI()

REDIS_URL_TEXT = getenv('REDIS_URL_TEXT', default="redis://172.18.0.3/0")
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)

HASH_SERVICE_URL = getenv('HASH_SERVICE_URL', default="http://hash-service:8002/generate-hash")


### Pydantic Models
class CreatePostRequest(BaseModel):
    text: str = Field(..., max_length=4500)
    ttl: int = Field(..., gt=0)


class CreatePostResponse(BaseModel):
    short_url: str


### UTILS
async def store_in_redis_or_db(short_hash: str, text: str, ttl: int):
    """Сохранение текста в Redis (если TTL короткий) или в БД."""
    logger.debug(f"Storing text with hash={short_hash}, ttl={ttl}")
    if ttl <= 10:  #3600:  # Если TTL <= 1 час
        try:
            await redis.set(short_hash, text, ex=ttl)
            logger.info(f"Text stored in Redis with hash={short_hash}")
        except Exception as e:
            logger.error(f"Error storing text in Redis: {e}")
    else:
        try:
            await store_in_db(short_hash, text, ttl)
            logger.info(f"Text stored in database with hash={short_hash}")
        except Exception as e:
            logger.error(f"Error storing text in database: {e}")


### ENDPOINTS
@app.on_event("startup")
async def on_startup():
    """ Инициализация при старте приложения. """
    logger.debug("Starting application initialization.")
    try:
        # Убедитесь, что база данных доступна
        await create_database()
        await ensure_db_ready()
        logger.info("Database is ready.")
        await create_tables()
        logger.info("Tables are created.")

        # Убедитесь, что Redis доступен
        global redis
        redis = await ensure_redis_ready(REDIS_URL_TEXT)
        logger.info("Redis is ready.")
    except Exception as e:
        logger.error(f"Error when starting the application: {e}")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """ Middleware для логирования запросов и измерения их времени. """
    logger.debug(f"Processing request: {request.method} {request.url}")
    start_time = time.time()
    response = await call_next(request)
    response_time = time.time() - start_time

    # Логируем и добавляем метрики
    log_request(request, response_time, response.status_code)
    logger.info(f"Request processed: {request.method} {request.url} in {response_time:.3f}s, status={response.status_code}")

    return response


@app.get("/metrics")
async def metrics():
    """
    Эндпоинт для отдачи метрик в формате, который Prometheus может собрать.
    """
    return Response(generate_latest(REGISTRY), media_type="text/plain")


@app.get("/")
async def root():
    logger.debug("Redirecting to /docs.")
    return RedirectResponse(url="/docs")


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest):
    logger.debug(f"Received create_post request: {request}")
    try:
        # Генерация уникального хэша
        async with aiohttp.ClientSession() as session:
            async with session.get(HASH_SERVICE_URL) as response:
                if response.status != 200:
                    error_detail = await response.text()
                    logger().error(f"Hash service error: {error_detail}")
                    raise HTTPException(status_code=response.status,
                                        detail=f"Error from hash service: {error_detail}")
                data = await response.json()
                short_hash = data['hash']
                logger.info(f"Hash generated: {short_hash}")

        # Сохранение в Redis или БД
        await store_in_redis_or_db(short_hash, request.text, request.ttl)

        # Генерация короткой ссылки
        short_url = f"http://localhost:8001/get/{short_hash}"

        return {"short_url": short_url}
    except Exception as e:
        logger.error(f"Error in create_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/get/{short_hash}")
async def get_post(short_hash: str):
    logger.debug(f"Received get_post request for hash={short_hash}")
    try:
        # Сначала пытаемся получить текст из Redis
        text = await redis.get(short_hash)

        if not text:
            logger.info(f"Hash {short_hash} not found in Redis, checking database.")
            result = await get_post_db(short_hash)

            if result:
                text = result["text"]

                # Кэшируем текст в Redis (redis_text)
                await redis.set(short_hash, text, ex=600)  # TTL = 600 секунд
                logger.info(f"Hash {short_hash} cached in Redis with TTL=600s.")
            else:
                logger.warning(f"Hash {short_hash} not found in database.")
                raise HTTPException(status_code=404, detail="Post not found")

        return {"text": text}
    except Exception as e:
        logger.error(f"Ошибка в get_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
