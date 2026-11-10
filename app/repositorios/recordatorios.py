"""Acceso a datos de Recordatorio."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.enums import EstadoRecordatorio
from app.modelos.recordatorio import Recordatorio


async def vencidos_pendientes(
    sesion: AsyncSession, ahora: datetime, limite: int = 100
) -> list[Recordatorio]:
    """Pendientes cuya hora ya llego. Bloquea filas (SKIP LOCKED) para evitar doble envio."""
    consulta = (
        select(Recordatorio)
        .where(
            Recordatorio.eliminado_en.is_(None),
            Recordatorio.estado == EstadoRecordatorio.PENDIENTE,
            Recordatorio.fecha_hora <= ahora,
        )
        .order_by(Recordatorio.fecha_hora)
        .limit(limite)
        .with_for_update(skip_locked=True)
    )
    return list((await sesion.execute(consulta)).scalars())
