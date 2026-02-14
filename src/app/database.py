"""
Database setup — async SQLAlchemy with SQLite (dev) or Postgres (prod).

get_db() is the FastAPI dependency that gives you a session per request.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from src.app.config import DATABASE_URL


# Create the async engine. check_same_thread=False needed for SQLite.
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, connect_args=connect_args)

# Session factory — each call produces a new async session
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db():
    """FastAPI dependency — yields a database session, auto-closes when done."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """Create all tables. Called on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
