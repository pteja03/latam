"""Acceso a datos de Doctor."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.doctor import Doctor


async def obtener(sesion: AsyncSession, id_doctor: uuid.UUID) -> Doctor | None:
    consulta = select(Doctor).where(Doctor.id == id_doctor, Doctor.eliminado_en.is_(None))
    return (await sesion.execute(consulta)).scalar_one_or_none()


async def listar(
    sesion: AsyncSession, *, ids: Sequence[uuid.UUID] | None = None, solo_activos: bool = False
) -> list[Doctor]:
    consulta = select(Doctor).where(Doctor.eliminado_en.is_(None)).order_by(Doctor.nombre)
    if ids is not None:
        consulta = consulta.where(Doctor.id.in_(ids))
    if solo_activos:
        consulta = consulta.where(Doctor.activo.is_(True))
    return list((await sesion.execute(consulta)).scalars())


async def obtener_por_telefonos(
    sesion: AsyncSession, telefonos_e164: Sequence[str]
) -> Doctor | None:
    """Doctor activo cuyo telefono coincide con alguno de los candidatos (WA-04)."""
    consulta = select(Doctor).where(
        Doctor.telefono_whatsapp.in_(telefonos_e164),
        Doctor.eliminado_en.is_(None),
        Doctor.activo.is_(True),
    )
    return (await sesion.execute(consulta)).scalars().first()
