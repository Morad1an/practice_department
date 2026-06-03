import asyncmy
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.app.config import settings


async def _open_asyncmy_connection():
    return await asyncmy.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        db=settings.DB_NAME,
    )


engine = create_async_engine("mysql+asyncmy://", async_creator=_open_asyncmy_connection)

async_session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
