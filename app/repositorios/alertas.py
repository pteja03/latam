"""Acceso a datos de AlertaRecepcion."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.enums import EstadoAlerta


def _base():  # noqa: ANN202
    return (
        select(AlertaRecepcion)
        .options(joinedload(AlertaRecepcion.doctor))
        .where(AlertaRecepcion.eliminado_en.is_(None))
    )


async def obtener(sesion: AsyncSession, id_alerta: uuid.UUID) -> AlertaRecepcion | None:
    consulta = _base().where(AlertaRecepcion.id == id_alerta)
    return (await sesion.execute(consulta)).scalar_one_or_none()


async def listar(
    sesion: AsyncSession,
    *,
    ids_doctor: Sequence[uuid.UUID] | None = None,
    estados: Sequence[EstadoAlerta] | None = None,
) -> list[AlertaRecepcion]:
    consulta = _base().order_by(AlertaRecepcion.creado_en.desc())
    if ids_doctor is not None:
        consulta = consulta.where(AlertaRecepcion.id_doctor.in_(ids_doctor))
    if estados:
        consulta = consulta.where(AlertaRecepcion.estado.in_(estados))
    return list((await sesion.execute(consulta)).scalars())


async def contar_pendientes(sesion: AsyncSession, ids_doctor: Sequence[uuid.UUID] | None) -> int:
    consulta = select(func.count()).where(
        AlertaRecepcion.eliminado_en.is_(None), AlertaRecepcion.estado == EstadoAlerta.PENDIENTE
    )
    if ids_doctor is not None:
        consulta = consulta.where(AlertaRecepcion.id_doctor.in_(ids_doctor))
    return (await sesion.execute(consulta)).scalar_one()
