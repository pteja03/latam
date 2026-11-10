"""Engine y sesion async de FastAPI. Celery NO usa este modulo (ver ARQ-07)."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import obtener_config


@lru_cache
def obtener_engine() -> AsyncEngine:
    return create_async_engine(obtener_config().database_url, pool_pre_ping=True)


@lru_cache
def obtener_fabrica_sesiones() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(obtener_engine(), expire_on_commit=False)


async def obtener_sesion() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI: confirma al terminar, revierte si hay error."""
    async with obtener_fabrica_sesiones()() as sesion:
        try:
            yield sesion
            await sesion.commit()
        except Exception:
            await sesion.rollback()
            raise
