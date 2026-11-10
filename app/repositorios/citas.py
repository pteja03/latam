"""Acceso a datos de Cita."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modelos.cita import Cita
from app.modelos.enums import EstadoCita


def _base():  # noqa: ANN202
    return select(Cita).options(joinedload(Cita.paciente)).where(Cita.eliminado_en.is_(None))


async def obtener(sesion: AsyncSession, id_cita: uuid.UUID) -> Cita | None:
    return (await sesion.execute(_base().where(Cita.id == id_cita))).scalar_one_or_none()


async def listar(
    sesion: AsyncSession,
    *,
    ids_doctor: Sequence[uuid.UUID] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    incluir_canceladas: bool = True,
) -> list[Cita]:
    """Citas que se traslapan con [desde, hasta)."""
    consulta = _base().order_by(Cita.fecha_hora_inicio)
    if ids_doctor is not None:
        consulta = consulta.where(Cita.id_doctor.in_(ids_doctor))
    if desde is not None:
        consulta = consulta.where(Cita.fecha_hora_fin > desde)
    if hasta is not None:
        consulta = consulta.where(Cita.fecha_hora_inicio < hasta)
    if not incluir_canceladas:
        consulta = consulta.where(Cita.estado != EstadoCita.CANCELADA)
    return list((await sesion.execute(consulta)).scalars())


async def contar_por_estado(
    sesion: AsyncSession,
    *,
    ids_doctor: Sequence[uuid.UUID] | None,
    desde: datetime,
    hasta: datetime,
) -> dict[EstadoCita, int]:
    consulta = (
        select(Cita.estado, func.count())
        .where(
            Cita.eliminado_en.is_(None),
            Cita.fecha_hora_inicio >= desde,
            Cita.fecha_hora_inicio < hasta,
        )
        .group_by(Cita.estado)
    )
    if ids_doctor is not None:
        consulta = consulta.where(Cita.id_doctor.in_(ids_doctor))
    return {estado: total for estado, total in (await sesion.execute(consulta)).all()}


async def obtener_para_sync(sesion: AsyncSession, id_cita: uuid.UUID) -> Cita | None:
    """Incluye citas eliminadas (soft delete): su evento de Google debe borrarse."""
    consulta = (
        select(Cita)
        .options(joinedload(Cita.paciente), joinedload(Cita.doctor))
        .where(Cita.id == id_cita)
    )
    return (await sesion.execute(consulta)).scalar_one_or_none()
