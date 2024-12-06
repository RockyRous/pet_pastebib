import hashlib

from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from db import create_tables, get_db, ensure_db_ready, ensure_redis_ready

### Настройки

# Инициализация Redis
REDIS_URL_TEXT = "redis://redis_text:6379/0"
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)

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
        global redis
        redis = await ensure_redis_ready()
    except Exception as e:
        print(f"Ошибка при старте приложения: {e}")


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

    # Сохраняем в Redis с TTL
    await redis.set(short_hash, request.text, ex=request.ttl)

    # Запись в таблицу posts (опционально, если нужно дублирование в БД)
    query = """
        INSERT INTO posts (hash, text, ttl, created_at)
        VALUES ($1, $2, $3, $4)
    """
    await db.execute(query, short_hash, request.text, request.ttl, datetime.utcnow())

    return {"short_url": short_url}


@app.get("/{short_hash}")
async def get_post(short_hash: str, db=Depends(get_db)):
    # Проверяем, есть ли текст в Redis
    cached_text = await redis.get(short_hash)
    if cached_text:
        return {"text": cached_text}

    # Если в Redis нет, проверяем в базе данных
    query = "SELECT text, ttl FROM posts WHERE hash = $1"
    post = await db.fetchrow(query, short_hash)

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Возвращаем текст поста
    return {"text": post['text']}
