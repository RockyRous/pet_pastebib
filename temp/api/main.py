from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import Column, String, Integer, DateTime, select
from sqlalchemy.ext.declarative import declarative_base
import httpx
import asyncio
from datetime import datetime, timedelta
import os

# Настройки
# Получение конфигурации из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/pastebin_text")
REDIS_URL_TEXT = os.getenv("REDIS_URL_TEXT", "redis://localhost:6379/0")
HASH_SERVICE_URL = os.getenv("HASH_SERVICE_URL", "http://localhost:8000") + '/generate_hash'
# Инициализация Redis
redis = Redis.from_url(REDIS_URL_TEXT, decode_responses=True)
# Инициализация FastAPI
app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))
# Инициализация подключения к базе данных
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"
    hash = Column(String, primary_key=True)
    text = Column(String, nullable=False)
    ttl = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Pydantic Models
class CreatePostRequest(BaseModel):
    text: str = Field(..., max_length=500)
    ttl: int = Field(..., gt=0)


class CreatePostResponse(BaseModel):
    short_url: str


async def create_tables():
    """ Асинхронная функция для создания таблиц """
    # Пытаемся создать таблицы в базе данных
    async with engine.begin() as conn:
        # Создаем все таблицы, если они не существуют
        await conn.run_sync(Base.metadata.create_all)


@app.on_event("startup")
async def on_startup():
    """ Вызов функции для создания таблиц при старте приложения """
    await create_tables()


@app.post("/create_post", response_model=CreatePostResponse)
async def create_post(request: CreatePostRequest, background_tasks: BackgroundTasks,
                      db: AsyncSession = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        # try:
        # Отправляем текст и TTL в hash_service
        response = await client.post(HASH_SERVICE_URL, json={"text": request.text, "ttl": request.ttl})
        response.raise_for_status()
        short_hash = response.json().get("short_hash")
        # except httpx.HTTPError as e:
        #     raise HTTPException(status_code=500, detail="Hash service error: " + str(e))

    # Создаем короткий URL
    short_url = f"http://localhost:8000/{short_hash}"

    # Добавляем фоновую задачу для записи в БД
    background_tasks.add_task(save_post_to_db, db, short_hash, request.text, request.ttl)

    return {"short_url": short_url}


@app.get("/{short_hash}")
async def get_post(short_hash: str, db: AsyncSession = Depends(get_db)):
    # Проверяем Redis
    text = await redis.get(short_hash)
    if text:
        return {"text": text}

    # Если в Redis нет, ищем в PostgreSQL
    query = select(Post).where(Post.hash == short_hash)
    result = await db.execute(query)
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Кэшируем в Redis с TTL/2
    await redis.set(short_hash, post.text, ex=post.ttl // 2)
    return {"text": post.text}


# Фоновые задачи
async def save_post_to_db(db: AsyncSession, short_hash: str, text: str, ttl: int):
    new_post = Post(hash=short_hash, text=text, ttl=ttl)
    db.add(new_post)
    await db.commit()


###################################################

# @app.get("/line_redis")
# def line_redis():
#     """ Подключение к Redis напрямую """
#     # Подключение к Redis (замените 'redis-node1' на имя или IP Master узла)
#     redis_client = redis.Redis(host='redis-node1', port=6379, db=0)
#
#     # Установка и получение значения
#     redis_client.set('my_key', 'my_value')
#     value = redis_client.get('my_key')
#     return value.decode('utf-8')  # my_value
#
#
# @app.get("/cache_redis")
# def cache_redis():
#     """ Кеширование запросов """
#     redis_client = redis.Redis(host='redis-node1', port=6379, db=0)
#
#     def get_data_with_cache(key):
#         # Попробовать получить данные из кеша
#         cached_data = redis_client.get(key)
#         if cached_data:
#             print("Из кеша")
#             return cached_data.decode('utf-8')
#
#         # Если данных нет, получить их, например, из базы данных
#         print("Получение из источника")
#         data = f"Data for {key}"  # Замените на реальный запрос
#         time.sleep(2)  # Симуляция задержки
#
#         # Сохранить данные в кеш с TTL = 60 секунд
#         redis_client.setex(key, 60, data)
#         return data
#
#     # Пример использования
#     return get_data_with_cache('test_key')


