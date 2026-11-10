"""Acceso a datos de UsuarioRecepcion."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.usuario_recepcion import UsuarioRecepcion


async def obtener(sesion: AsyncSession, id_usuario: uuid.UUID) -> UsuarioRecepcion | None:
    consulta = select(UsuarioRecepcion).where(
        UsuarioRecepcion.id == id_usuario, UsuarioRecepcion.eliminado_en.is_(None)
    )
    return (await sesion.execute(consulta)).scalar_one_or_none()


async def obtener_por_correo(sesion: AsyncSession, correo: str) -> UsuarioRecepcion | None:
    consulta = select(UsuarioRecepcion).where(
        func.lower(UsuarioRecepcion.correo) == correo.strip().lower(),
        UsuarioRecepcion.eliminado_en.is_(None),
    )
    return (await sesion.execute(consulta)).scalar_one_or_none()


async def listar(sesion: AsyncSession) -> list[UsuarioRecepcion]:
    consulta = (
        select(UsuarioRecepcion)
        .where(UsuarioRecepcion.eliminado_en.is_(None))
        .order_by(UsuarioRecepcion.nombre)
    )
    return list((await sesion.execute(consulta)).scalars())
