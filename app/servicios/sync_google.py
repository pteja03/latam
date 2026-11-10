"""Sincronizacion de citas con Google Calendar (GC-01, GC-02)."""

import uuid
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.cita import Cita
from app.modelos.doctor import Doctor
from app.modelos.enums import EstadoCita, EstadoSyncGoogle
from app.repositorios import auditoria
from app.repositorios import citas as repo
from app.servicios import alertas


class CalendarioExterno(Protocol):
    async def crear_evento(self, doctor: Doctor, evento: dict[str, Any]) -> str: ...
    async def actualizar_evento(
        self, doctor: Doctor, id_evento: str, evento: dict[str, Any]
    ) -> None: ...
    async def eliminar_evento(self, doctor: Doctor, id_evento: str) -> None: ...


def construir_evento(cita: Cita) -> dict[str, Any]:
    """GC-01: sin datos clinicos. Solo "Consulta" + nombre del paciente."""
    return {
        "summary": f"Consulta - {cita.paciente.nombre_completo}",
        "start": {"dateTime": cita.fecha_hora_inicio.isoformat()},
        "end": {"dateTime": cita.fecha_hora_fin.isoformat()},
    }


async def sincronizar_cita(
    sesion: AsyncSession, id_cita: uuid.UUID, calendario: CalendarioExterno
) -> None:
    """Crea, actualiza o borra el evento. Lanza excepcion si Google falla (el worker reintenta)."""
    cita = await repo.obtener_para_sync(sesion, id_cita)
    if cita is None or cita.doctor.credenciales_google_calendar is None:
        return  # doctor sin Google Calendar conectado: queda 'pendiente'
    inactiva = cita.eliminado_en is not None or cita.estado == EstadoCita.CANCELADA
    if inactiva:
        if cita.id_evento_google:
            await calendario.eliminar_evento(cita.doctor, cita.id_evento_google)
            cita.id_evento_google = None
    elif cita.id_evento_google:
        await calendario.actualizar_evento(
            cita.doctor, cita.id_evento_google, construir_evento(cita)
        )
    else:
        cita.id_evento_google = await calendario.crear_evento(cita.doctor, construir_evento(cita))
    cita.estado_sync_google = EstadoSyncGoogle.SINCRONIZADO
    await sesion.flush()


async def marcar_error(sesion: AsyncSession, id_cita: uuid.UUID) -> None:
    """GC-02: reintentos agotados -> estado error + alerta a recepcion."""
    cita = await repo.obtener_para_sync(sesion, id_cita)
    if cita is None:
        return
    cita.estado_sync_google = EstadoSyncGoogle.ERROR
    await alertas.crear(
        sesion,
        id_doctor=cita.id_doctor,
        mensaje_ia="No se pudo sincronizar una cita con Google Calendar tras varios intentos.",
        instruccion_original=(
            f"Revisar en el calendario del doctor la cita de {cita.paciente.nombre_completo} "
            f"del {cita.fecha_hora_inicio.isoformat(timespec='minutes')} (UTC)."
        ),
        actor=auditoria.ACTOR_SISTEMA,
    )
