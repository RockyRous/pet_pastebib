from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select
from datetime import datetime, timedelta
import hashlib
import os
import asyncio

# Настройки
# Получение конфигурации из переменных окружения
# Инициализация FastAPI
app = FastAPI(root_path=os.getenv("ROOT_PATH", ""))
# Инициализация подключения к базе данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@postgres-hash:5432/pastebin_hash")
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


Base = declarative_base()

class Hash(Base):
    __tablename__ = "hashes"
    short_hash = Column(String, primary_key=True)
    text = Column(String, nullable=False)
    ttl = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Уникальный индекс
    __table_args__ = (UniqueConstraint("short_hash", name="uq_short_hash"),)


# Pydantic Models
class GenerateHashRequest(BaseModel):
    text: str
    ttl: int


class GenerateHashResponse(BaseModel):
    short_hash: str


def generate_unique_hash(text: str) -> str:
    """ Функция для генерации уникального хеша """
    hash_object = hashlib.md5(text.encode())
    return hash_object.hexdigest()[:8]


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

# Эндпоинты
@app.post("/generate_hash", response_model=GenerateHashResponse)
async def generate_hash(request: GenerateHashRequest, db: AsyncSession = Depends(get_db)):
    attempt = 0
    while attempt < 5:  # Ограничиваем количество попыток
        # Генерация уникального хэша с солью (например, текущей датой)
        short_hash = generate_unique_hash(request.text + str(datetime.utcnow()) + str(attempt))

        # Проверка наличия хэша в БД
        query = select(Hash).where(Hash.short_hash == short_hash)
        result = await db.execute(query)
        existing_hash = result.scalar_one_or_none()  # Используем scalar_one_or_none

        if not existing_hash:
            # Если хэш уникален, сохраняем его
            new_hash = Hash(short_hash=short_hash, text=request.text, ttl=request.ttl, created_at=datetime.utcnow())
            db.add(new_hash)
            await db.commit()
            return {"short_hash": short_hash}

        attempt += 1

    raise HTTPException(status_code=500, detail="Unable to generate unique hash after multiple attempts")
