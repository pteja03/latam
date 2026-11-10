"""Logica de alertas a recepcion (DAT-07, human-in-the-loop)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.enums import EstadoAlerta
from app.repositorios import auditoria


class TransicionInvalida(Exception):
    pass


async def crear(
    sesion: AsyncSession,
    *,
    id_doctor: uuid.UUID,
    mensaje_ia: str,
    instruccion_original: str,
    actor: str,
) -> AlertaRecepcion:
    alerta = AlertaRecepcion(
        id_doctor=id_doctor, mensaje_ia=mensaje_ia, instruccion_original=instruccion_original
    )
    sesion.add(alerta)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="alerta_recepcion",
        id_entidad=alerta.id,
        accion="crear",
        actor=actor,
        cambios={"id_doctor": id_doctor},
    )
    return alerta


async def tomar(sesion: AsyncSession, alerta: AlertaRecepcion, id_usuario: uuid.UUID) -> None:
    if alerta.estado != EstadoAlerta.PENDIENTE:
        raise TransicionInvalida("La alerta ya fue tomada o resuelta")
    alerta.estado = EstadoAlerta.EN_PROCESO
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="alerta_recepcion",
        id_entidad=alerta.id,
        accion="tomar",
        actor=auditoria.actor_usuario(id_usuario),
        cambios={"estado": alerta.estado},
    )


async def resolver(sesion: AsyncSession, alerta: AlertaRecepcion, id_usuario: uuid.UUID) -> None:
    if alerta.estado == EstadoAlerta.RESUELTA:
        raise TransicionInvalida("La alerta ya esta resuelta")
    alerta.estado = EstadoAlerta.RESUELTA
    alerta.resuelta_por = id_usuario
    alerta.resuelta_en = datetime.now(UTC)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="alerta_recepcion",
        id_entidad=alerta.id,
        accion="resolver",
        actor=auditoria.actor_usuario(id_usuario),
        cambios={"estado": alerta.estado},
    )
