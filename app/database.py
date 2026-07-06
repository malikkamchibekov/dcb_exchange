from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Асинхронный engine — единственное соединение-пул на всё приложение.
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# Фабрика сессий. expire_on_commit=False — чтобы после commit() можно было
# читать атрибуты объекта без лишнего запроса в БД
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    # Dependency для FastAPI: открывает сессию на время запроса и закрывает её
    # автоматически по выходу из "async with", даже если внутри было исключение.
    async with async_session_factory() as session:
        yield session