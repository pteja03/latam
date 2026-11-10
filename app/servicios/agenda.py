"""Logica de agenda: citas, antisolapamiento (DAT-05) y disponibilidad (IA-07)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obtener_config
from app.modelos.cita import NOMBRE_CONSTRAINT_SOLAPE, Cita
from app.modelos.doctor import Doctor
from app.modelos.enums import EstadoCita, EstadoSyncGoogle, OrigenCita
from app.repositorios import auditoria
from app.repositorios import citas as repo

MAX_ALTERNATIVAS = 3


class HorarioOcupado(Exception):
    """El horario choca con otra cita del doctor. Incluye alternativas libres."""

    def __init__(self, alternativas: list[datetime]) -> None:
        super().__init__("horario ocupado")
        self.alternativas = alternativas


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def limites_del_dia(fecha: date, zona: str) -> tuple[datetime, datetime]:
    """Inicio y fin (UTC) del dia local `fecha` en la zona indicada."""
    tz = ZoneInfo(zona)
    inicio = datetime.combine(fecha, time.min, tzinfo=tz)
    fin = datetime.combine(fecha + timedelta(days=1), time.min, tzinfo=tz)
    return inicio.astimezone(UTC), fin.astimezone(UTC)


def _es_solape(error: IntegrityError) -> bool:
    return NOMBRE_CONSTRAINT_SOLAPE in str(error.orig)


async def huecos_libres(
    sesion: AsyncSession, doctor: Doctor, fecha: date, duracion_min: int
) -> list[datetime]:
    """Inicios libres (en zona del doctor) dentro de la jornada del dia local `fecha`."""
    cfg = obtener_config()
    tz = ZoneInfo(doctor.zona_horaria)
    apertura = datetime.combine(fecha, time(cfg.jornada_hora_inicio), tzinfo=tz)
    cierre = datetime.combine(fecha, time(cfg.jornada_hora_fin), tzinfo=tz)
    ocupadas = await repo.listar(
        sesion, ids_doctor=[doctor.id], desde=apertura, hasta=cierre, incluir_canceladas=False
    )
    paso = timedelta(minutes=duracion_min)
    ahora = ahora_utc()
    libres: list[datetime] = []
    cursor = apertura
    while cursor + paso <= cierre:
        fin = cursor + paso
        choca = any(c.fecha_hora_inicio < fin and c.fecha_hora_fin > cursor for c in ocupadas)
        if not choca and cursor > ahora:
            libres.append(cursor)
        cursor = fin
    return libres


async def _alternativas(
    sesion: AsyncSession, doctor: Doctor, inicio: datetime, duracion_min: int
) -> list[datetime]:
    """Huecos mas cercanos a la hora pedida; si el dia esta lleno, prueba los 2 siguientes."""
    fecha_local = inicio.astimezone(ZoneInfo(doctor.zona_horaria)).date()
    for desplazamiento in range(3):
        libres = await huecos_libres(
            sesion, doctor, fecha_local + timedelta(days=desplazamiento), duracion_min
        )
        if libres:
            libres.sort(key=lambda h: abs((h - inicio).total_seconds()))
            return sorted(libres[:MAX_ALTERNATIVAS])
    return []


async def crear_cita(
    sesion: AsyncSession,
    *,
    doctor: Doctor,
    id_paciente: uuid.UUID,
    inicio: datetime,
    fin: datetime | None,
    motivo: str | None,
    origen: OrigenCita,
    actor: str,
) -> Cita:
    if fin is None:
        fin = inicio + timedelta(minutes=doctor.duracion_cita_default_min)
    cita = Cita(
        id_doctor=doctor.id,
        id_paciente=id_paciente,
        fecha_hora_inicio=inicio.astimezone(UTC),
        fecha_hora_fin=fin.astimezone(UTC),
        motivo_consulta=motivo,
        origen=origen,
    )
    try:
        async with sesion.begin_nested():
            sesion.add(cita)
            await sesion.flush()
    except IntegrityError as error:
        if not _es_solape(error):
            raise
        minutos = int((fin - inicio).total_seconds() // 60)
        raise HorarioOcupado(await _alternativas(sesion, doctor, inicio, minutos)) from None
    await auditoria.registrar(
        sesion,
        entidad="cita",
        id_entidad=cita.id,
        accion="crear",
        actor=actor,
        cambios={
            "id_doctor": doctor.id,
            "id_paciente": id_paciente,
            "fecha_hora_inicio": cita.fecha_hora_inicio,
            "fecha_hora_fin": cita.fecha_hora_fin,
            "motivo_consulta": motivo,
            "origen": origen,
        },
    )
    cita_completa = await repo.obtener(sesion, cita.id)
    assert cita_completa is not None
    return cita_completa


async def actualizar_cita(
    sesion: AsyncSession, *, cita: Cita, doctor: Doctor, cambios: dict[str, Any], actor: str
) -> Cita:
    """Aplica cambios (horario, motivo, estados). Reprogramar revalida DAT-05."""
    inicio = cambios.get("fecha_hora_inicio", cita.fecha_hora_inicio)
    fin = cambios.get("fecha_hora_fin")
    if fin is None:
        # Si solo se mueve el inicio, se conserva la duracion.
        fin = inicio + (cita.fecha_hora_fin - cita.fecha_hora_inicio)
    if fin <= inicio:
        raise ValueError("fecha_hora_fin debe ser posterior a fecha_hora_inicio")
    cambia_horario = (inicio, fin) != (cita.fecha_hora_inicio, cita.fecha_hora_fin)
    try:
        async with sesion.begin_nested():
            for campo in ("motivo_consulta", "estado", "estado_seguimiento"):
                if campo in cambios:
                    setattr(cita, campo, cambios[campo])
            cita.fecha_hora_inicio = inicio.astimezone(UTC)
            cita.fecha_hora_fin = fin.astimezone(UTC)
            if cambia_horario or cambios.get("estado") == EstadoCita.CANCELADA:
                cita.estado_sync_google = EstadoSyncGoogle.PENDIENTE
            await sesion.flush()
    except IntegrityError as error:
        await sesion.refresh(cita)
        if not _es_solape(error):
            raise
        minutos = int((fin - inicio).total_seconds() // 60)
        raise HorarioOcupado(await _alternativas(sesion, doctor, inicio, minutos)) from None
    await auditoria.registrar(
        sesion,
        entidad="cita",
        id_entidad=cita.id,
        accion="actualizar",
        actor=actor,
        cambios=cambios,
    )
    return cita


async def eliminar_cita(sesion: AsyncSession, *, cita: Cita, actor: str) -> None:
    """Soft delete: nunca DELETE fisico."""
    cita.eliminado_en = ahora_utc()
    cita.estado_sync_google = EstadoSyncGoogle.PENDIENTE
    await sesion.flush()
    await auditoria.registrar(
        sesion, entidad="cita", id_entidad=cita.id, accion="eliminar", actor=actor
    )
