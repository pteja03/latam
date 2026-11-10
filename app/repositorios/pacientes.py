"""Acceso a datos de Paciente."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.paciente import Paciente


async def obtener(sesion: AsyncSession, id_paciente: uuid.UUID) -> Paciente | None:
    consulta = select(Paciente).where(Paciente.id == id_paciente, Paciente.eliminado_en.is_(None))
    return (await sesion.execute(consulta)).scalar_one_or_none()


async def buscar_por_nombre_normalizado(
    sesion: AsyncSession, palabras: list[str], limite: int = 20
) -> list[Paciente]:
    """Coincide si TODAS las palabras aparecen en nombre_normalizado."""
    consulta = select(Paciente).where(Paciente.eliminado_en.is_(None))
    for palabra in palabras:
        seguro = palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.where(Paciente.nombre_normalizado.like(f"%{seguro}%", escape="\\"))
    consulta = consulta.order_by(Paciente.nombre_normalizado).limit(limite)
    return list((await sesion.execute(consulta)).scalars())
