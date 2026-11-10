"""Cierre nocturno (IA-15..17) y envio de recordatorios (IA-18)."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obtener_config
from app.integraciones.gemini.orquestador import clave_cierre_pendiente
from app.modelos.doctor import Doctor
from app.modelos.enums import EstadoCita, EstadoRecordatorio
from app.repositorios import citas as repo_citas
from app.repositorios import doctores as repo_doctores
from app.repositorios import recordatorios as repo_recordatorios
from app.servicios import agenda
from app.servicios.mensajes import clave_ventana

log = logging.getLogger(__name__)

TTL_MARCA_CIERRE_SEG = 36 * 3600
TTL_PREGUNTA_CIERRE_SEG = 12 * 3600
_SIN_CERRAR = (
    EstadoCita.PROGRAMADA,
    EstadoCita.CONFIRMADA,
    EstadoCita.EN_ESPERA,
    EstadoCita.EN_CONSULTA,
)


class EnvioWhatsApp(Protocol):
    async def enviar_texto(self, telefono: str, texto: str) -> None: ...
    async def enviar_plantilla(self, telefono: str, nombre: str, parametros: list[str]) -> None: ...


async def doctores_en_cierre(
    sesion: AsyncSession, redis: Redis, ahora: datetime
) -> list[uuid.UUID]:
    """IA-15: doctores que ya pasaron su hora_cierre_diario local y aun no reciben resumen hoy."""
    pendientes: list[uuid.UUID] = []
    for doctor in await repo_doctores.listar(sesion, solo_activos=True):
        local = ahora.astimezone(ZoneInfo(doctor.zona_horaria))
        if local.time() < doctor.hora_cierre_diario:
            continue
        marca = f"cierre:{doctor.id}:{local.date().isoformat()}"
        if await redis.set(marca, "1", nx=True, ex=TTL_MARCA_CIERRE_SEG):
            pendientes.append(doctor.id)
    return pendientes


async def enviar_resumen_cierre(
    sesion: AsyncSession, redis: Redis, wa: EnvioWhatsApp, doctor: Doctor, ahora: datetime
) -> None:
    cfg = obtener_config()
    hoy = ahora.astimezone(ZoneInfo(doctor.zona_horaria)).date()
    desde, hasta = agenda.limites_del_dia(hoy, doctor.zona_horaria)
    conteo = await repo_citas.contar_por_estado(
        sesion, ids_doctor=[doctor.id], desde=desde, hasta=hasta
    )
    manana = await repo_citas.contar_por_estado(
        sesion, ids_doctor=[doctor.id], desde=hasta, hasta=hasta + timedelta(days=1)
    )
    atendidas = conteo.get(EstadoCita.ATENDIDA, 0)
    sin_cerrar = sum(conteo.get(e, 0) for e in _SIN_CERRAR)
    citas_manana = sum(t for e, t in manana.items() if e != EstadoCita.CANCELADA)
    # IA-16: siempre por plantilla aprobada (puede estar fuera de la ventana de 24 h).
    await wa.enviar_plantilla(
        doctor.telefono_whatsapp,
        cfg.wa_plantilla_cierre,
        [doctor.nombre, str(atendidas), str(sin_cerrar), str(citas_manana)],
    )
    # IA-17: se recuerda la pregunta para interpretar la respuesta del doctor en contexto.
    pregunta = (
        f"Resumen del día: {atendidas} citas atendidas, {sin_cerrar} sin cerrar y "
        f"{citas_manana} citas para mañana. ¿Hay pendientes o seguimientos que quieras registrar?"
    )
    await redis.set(clave_cierre_pendiente(doctor.id), pregunta, ex=TTL_PREGUNTA_CIERRE_SEG)


async def enviar_recordatorios_vencidos(
    sesion: AsyncSession, redis: Redis, wa: EnvioWhatsApp, ahora: datetime
) -> int:
    """IA-18: envia los recordatorios cuya hora llego. Devuelve cuantos se enviaron."""
    cfg = obtener_config()
    enviados = 0
    for recordatorio in await repo_recordatorios.vencidos_pendientes(sesion, ahora):
        doctor = await repo_doctores.obtener(sesion, recordatorio.id_doctor)
        if doctor is None or not doctor.activo:
            recordatorio.estado = EstadoRecordatorio.CANCELADO
            continue
        try:
            if await redis.exists(clave_ventana(doctor.id)):
                await wa.enviar_texto(
                    doctor.telefono_whatsapp, f"Recordatorio: {recordatorio.descripcion}"
                )
            else:
                await wa.enviar_plantilla(
                    doctor.telefono_whatsapp,
                    cfg.wa_plantilla_recordatorio,
                    [recordatorio.descripcion],
                )
        except Exception as error:
            # Queda pendiente y se reintenta en el siguiente ciclo.
            log.error("No se pudo enviar un recordatorio: %s", type(error).__name__)
            continue
        recordatorio.estado = EstadoRecordatorio.ENVIADO
        enviados += 1
    await sesion.flush()
    return enviados
