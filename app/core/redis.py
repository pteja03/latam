"""Cliente Redis async. Cada proceso/tarea crea el suyo (no se comparte entre event loops).

En modo local (ARQ-08) no hay Redis: se devuelve un almacen equivalente sobre PostgreSQL.
"""

from typing import Any

from redis.asyncio import Redis

from app.core.config import obtener_config


def crear_redis() -> Any:
    cfg = obtener_config()
    if cfg.modo_local:
        from app.core.almacen_local import AlmacenLocal
        from app.db.sesion import obtener_engine

        return AlmacenLocal(obtener_engine())
    return Redis.from_url(cfg.redis_url, decode_responses=True)
