"""Cliente Redis async. Cada proceso/tarea crea el suyo (no se comparte entre event loops)."""

from redis.asyncio import Redis

from app.core.config import obtener_config


def crear_redis() -> Redis:
    return Redis.from_url(obtener_config().redis_url, decode_responses=True)
