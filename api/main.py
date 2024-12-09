import hashlib
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from os import getenv

from db import create_tables, get_db, ensure_db_ready, ensure_redis_ready

### Настройки

# Инициализация Redis
REDIS_URL_TEXT = getenv('REDIS_URL_TEXT', default="redis://172.18.0.3/0")
REDIS_URL_HASH = getenv('REDIS_URL_HASH', default="redis://172.18.0.2/0")

redis_text = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)
redis_hash = Redis.from_url(REDIS_URL_HASH, decode_responses=True)


# Инициализация FastAPI
app = FastAPI()

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

@app.on_event("startup")
async def on_startup():
    """Инициализация при старте приложения."""
    try:
        # Убедитесь, что база данных доступна
        await ensure_db_ready()
        await create_tables()

        # Убедитесь, что Redis доступен
        global redis_text, redis_hash
        redis_text = await ensure_redis_ready(REDIS_URL_TEXT)
        redis_hash = await ensure_redis_ready(REDIS_URL_HASH)
    except Exception as e:
        print(f"Ошибка при старте приложения: {e}")


def generate_unique_hash(text: str, length=8) -> str:
    unique_data = f"{text}{datetime.utcnow().timestamp()}"
    return hashlib.sha256(unique_data.encode()).hexdigest()[:length]


# Генерация хэша и проверка уникальности
async def generate_hash(request: dict, db) -> dict:
    attempt = 0
    while attempt < 10:
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


async def store_in_redis_or_db(short_hash: str, text: str, ttl: int, db):
    """Сохранение текста в Redis (если TTL короткий) или в БД."""
    if ttl <= 3600:  # Если TTL <= 1 час
        # Сохраняем текст в Redis (redis_text)
        await redis_text.set(short_hash, text, ex=ttl)
    else:
        # Сохраняем текст в БД
        query = """
            INSERT INTO posts (hash, text, ttl, created_at)
            VALUES ($1, $2, $3, $4)
        """
        await db.execute(query, short_hash, text, ttl, datetime.utcnow())

    # Сохраняем хэш в Redis (redis_hash)
    await redis_hash.set(short_hash, ttl, ex=ttl)


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest, db=Depends(get_db)):
    try:
        # Генерация уникального хэша
        short_hash = generate_unique_hash(request.text)

        # Сохранение в Redis или БД
        await store_in_redis_or_db(short_hash, request.text, request.ttl, db)

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
        text = await redis_text.get(short_hash)

        if not text:
            # Если текста нет в Redis, ищем его в БД
            query = "SELECT text FROM posts WHERE hash = $1"
            result = await db.fetchrow(query, short_hash)

            if result:
                text = result["text"]

                # Кэшируем текст в Redis (redis_text)
                await redis_text.set(short_hash, text, ex=600)  # TTL = 600 секунд
            else:
                raise HTTPException(status_code=404, detail="Post not found")

        return {"text": text}
    except Exception as e:
        print(f"Ошибка в get_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


