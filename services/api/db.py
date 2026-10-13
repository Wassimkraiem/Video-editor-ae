"""Async SQLAlchemy database boundary used by the production repository.

The local API uses `MemoryRepository` so the app is runnable without a
database. Deployments set `DATABASE_URL` to PostgreSQL and use this engine in
the repository implementation.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
