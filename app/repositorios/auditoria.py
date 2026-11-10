"""Registro en log_auditoria (DAT-09). Nunca guarda campos cifrados en claro."""

import uuid
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.log_auditoria import LogAuditoria

CAMPOS_CIFRADOS = frozenset(
    {
        "motivo_consulta",
        "notas_clinicas_breves",
        "credenciales_google_calendar",
        "mensaje_ia",
        "instruccion_original",
        "descripcion",
        "hash_password",
        "password",
    }
)
MARCA_CIFRADO = "[cifrado]"


def _serializar(valor: Any) -> Any:
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, datetime | date | time):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, dict):
        return sanear_cambios(valor)
    if isinstance(valor, list | tuple):
        return [_serializar(v) for v in valor]
    return valor


def sanear_cambios(cambios: dict[str, Any]) -> dict[str, Any]:
    return {
        k: MARCA_CIFRADO if k in CAMPOS_CIFRADOS else _serializar(v) for k, v in cambios.items()
    }


def actor_usuario(id_usuario: uuid.UUID) -> str:
    return f"usuario:{id_usuario}"


def actor_ia(id_doctor: uuid.UUID) -> str:
    return f"ia:{id_doctor}"


ACTOR_SISTEMA = "sistema"


async def registrar(
    sesion: AsyncSession,
    *,
    entidad: str,
    id_entidad: uuid.UUID,
    accion: str,
    actor: str,
    cambios: dict[str, Any] | None = None,
) -> LogAuditoria:
    log = LogAuditoria(
        entidad=entidad,
        id_entidad=id_entidad,
        accion=accion,
        actor=actor,
        cambios=sanear_cambios(cambios or {}),
    )
    sesion.add(log)
    await sesion.flush()
    return log
