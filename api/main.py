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


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest, db=Depends(get_db)):
    try:
        # Проверяем входные данные
        print(f"Request received: text={request.text}, ttl={request.ttl}")

        # Генерация уникального хэша
        short_hash = generate_unique_hash(request.text)
        print(f"Generated short_hash: {short_hash}")

        # Сохранение в Redis
        saved_to_redis = await redis.set(short_hash, request.text, ex=request.ttl)
        print(f"Saved to Redis: {saved_to_redis}")
        if not saved_to_redis:
            raise HTTPException(status_code=500, detail="Failed to save post to Redis")

        # Сохранение в БД
        query = """
            INSERT INTO posts (hash, text, ttl, created_at)
            VALUES ($1, $2, $3, $4)
        """
        await db.execute(query, short_hash, request.text, request.ttl, datetime.utcnow())
        print("Saved to DB successfully")

        # Генерация короткой ссылки
        short_url = f"http://localhost:8001/{short_hash}"
        print(f"Short URL created: {short_url}")

        return {"short_url": short_url}
    except Exception as e:
        print(f"Error during create_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/{short_hash}")
async def get_post(short_hash: str, db=Depends(get_db)):
    # Извлекаем только сам хэш из URL, если передана полная ссылка
    if short_hash.startswith("http://") or short_hash.startswith("https://"):
        short_hash = short_hash.rsplit("/", 1)[-1]

    # Проверка данных в Redis
    text = await redis.get(short_hash)

    if text is None:
        # Если в Redis нет данных, проверяем в базе данных
        query = "SELECT text FROM posts WHERE hash = :short_hash"
        result = await db.fetch_one(query, values={"short_hash": short_hash})

        if result:
            text = result["text"]
            # Сохраняем данные в Redis для будущих запросов
            await redis.set(short_hash, text, ex=600)  # TTL = 600 секунд
        else:
            # Если данных нет в базе данных, возвращаем ошибку 404
            raise HTTPException(status_code=404, detail="Post not found")

    # Возвращаем текст, который был найден в Redis или базе данных
    return {"text": text}
