"""Almacen clave-valor sobre PostgreSQL con la misma interfaz que usamos de Redis (ARQ-08).

Cubre solo las operaciones que la aplicacion necesita: idempotencia del webhook, historial de
chat, ventana de 24 h, limite por doctor y marcas del cierre nocturno. Los valores se guardan
cifrados. Es un cache tecnico con caducidad: las claves vencidas si se borran fisicamente.
"""

import json
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.cifrado import cifrar, descifrar

_VIGENTE = "(expira_en IS NULL OR expira_en > now())"


def _empacar(valor: Any) -> str:
    return cifrar(json.dumps(valor))


def _desempacar(crudo: str) -> Any:
    return json.loads(descifrar(crudo))


class AlmacenLocal:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def aclose(self) -> None:
        """Compatibilidad con Redis: el engine es compartido y no se cierra aqui."""

    async def _leer(self, clave: str) -> Any:
        async with self._engine.connect() as conexion:
            fila = (
                await conexion.execute(
                    text(f"SELECT valor FROM almacen_clave_valor WHERE clave = :c AND {_VIGENTE}"),
                    {"c": clave},
                )
            ).first()
        return None if fila is None else _desempacar(fila[0])

    async def _modificar(self, clave: str, cambio: Callable[[Any], Any]) -> Any:
        """Lee, transforma y guarda de forma atomica (bloqueo de fila)."""
        async with self._engine.begin() as conexion:
            await conexion.execute(
                text(
                    "INSERT INTO almacen_clave_valor (id, clave, valor, expira_en) "
                    "VALUES (:i, :c, :v, now()) ON CONFLICT (clave) DO NOTHING"
                ),
                {"i": uuid.uuid4(), "c": clave, "v": _empacar(None)},
            )
            fila = (
                await conexion.execute(
                    text(
                        "SELECT valor, expira_en IS NOT NULL AND expira_en <= now() "
                        "FROM almacen_clave_valor WHERE clave = :c FOR UPDATE"
                    ),
                    {"c": clave},
                )
            ).one()
            vencida = bool(fila[1])
            nuevo = cambio(None if vencida else _desempacar(fila[0]))
            await self._guardar(conexion, clave, nuevo, quitar_caducidad=vencida)
        return nuevo

    @staticmethod
    async def _guardar(
        conexion: AsyncConnection, clave: str, valor: Any, quitar_caducidad: bool
    ) -> None:
        caducidad = ", expira_en = NULL" if quitar_caducidad else ""
        await conexion.execute(
            text(
                f"UPDATE almacen_clave_valor SET valor = :v, actualizado_en = now(){caducidad} "
                "WHERE clave = :c"
            ),
            {"c": clave, "v": _empacar(valor)},
        )

    # ---------- operaciones estilo Redis ----------
    async def set(self, clave: str, valor: Any, nx: bool = False, ex: int | None = None) -> bool:
        async with self._engine.begin() as conexion:
            fila = (
                await conexion.execute(
                    text(
                        "INSERT INTO almacen_clave_valor (id, clave, valor, expira_en) "
                        "VALUES (:i, :c, :v, now() + make_interval(secs => :ex)) "
                        "ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor, "
                        "expira_en = EXCLUDED.expira_en, actualizado_en = now() "
                        "WHERE (NOT :nx) OR (almacen_clave_valor.expira_en IS NOT NULL "
                        "AND almacen_clave_valor.expira_en <= now()) RETURNING 1"
                    ),
                    {"i": uuid.uuid4(), "c": clave, "v": _empacar(valor), "ex": ex, "nx": nx},
                )
            ).first()
        return fila is not None

    async def get(self, clave: str) -> Any:
        return await self._leer(clave)

    async def exists(self, clave: str) -> int:
        async with self._engine.connect() as conexion:
            fila = (
                await conexion.execute(
                    text(f"SELECT 1 FROM almacen_clave_valor WHERE clave = :c AND {_VIGENTE}"),
                    {"c": clave},
                )
            ).first()
        return int(fila is not None)

    async def delete(self, *claves: str) -> int:
        async with self._engine.begin() as conexion:
            resultado = await conexion.execute(
                text("DELETE FROM almacen_clave_valor WHERE clave = ANY(:c)"), {"c": list(claves)}
            )
        return resultado.rowcount or 0

    async def incr(self, clave: str) -> int:
        return await self._modificar(clave, lambda actual: int(actual or 0) + 1)

    async def expire(self, clave: str, segundos: int) -> bool:
        async with self._engine.begin() as conexion:
            resultado = await conexion.execute(
                text(
                    "UPDATE almacen_clave_valor SET expira_en = now() + make_interval(secs => :s) "
                    f"WHERE clave = :c AND {_VIGENTE}"
                ),
                {"c": clave, "s": segundos},
            )
        return bool(resultado.rowcount)

    async def rpush(self, clave: str, *valores: str) -> int:
        lista = await self._modificar(clave, lambda actual: [*(actual or []), *valores])
        return len(lista)

    async def lrange(self, clave: str, inicio: int, fin: int) -> list[str]:
        lista = await self._leer(clave) or []
        return lista[inicio:] if fin == -1 else lista[inicio : fin + 1]

    async def ltrim(self, clave: str, inicio: int, fin: int) -> bool:
        def recortar(actual: Any) -> list[str]:
            lista = actual or []
            return lista[inicio:] if fin == -1 else lista[inicio : fin + 1]

        await self._modificar(clave, recortar)
        return True

    async def purgar_vencidas(self) -> int:
        async with self._engine.begin() as conexion:
            resultado = await conexion.execute(
                text(
                    "DELETE FROM almacen_clave_valor "
                    "WHERE expira_en IS NOT NULL AND expira_en <= now()"
                )
            )
        return resultado.rowcount or 0
