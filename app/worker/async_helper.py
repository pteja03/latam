"""ARQ-07: Celery es sincrono. Cada tarea corre su corrutina en un event loop propio,
con su propio engine/sesion y su propio cliente Redis. Nunca se comparte la sesion de FastAPI.
"""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import obtener_config
from app.core.redis import crear_redis

T = TypeVar("T")


def run_async(corrutina: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(corrutina)


@dataclass
class ContextoTarea:
    sesion: AsyncSession
    redis: Redis


@asynccontextmanager
async def contexto_tarea() -> AsyncIterator[ContextoTarea]:
    """Engine + sesion + Redis de vida igual a la tarea. Confirma al salir sin error."""
    engine = create_async_engine(
        obtener_config().database_url, poolclass=NullPool, hide_parameters=True
    )
    redis = crear_redis()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as sesion:
            try:
                yield ContextoTarea(sesion=sesion, redis=redis)
                await sesion.commit()
            except Exception:
                await sesion.rollback()
                raise
    finally:
        await redis.aclose()
        await engine.dispose()
