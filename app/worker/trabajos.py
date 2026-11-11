"""Cuerpo asincrono de cada tarea, sin depender de Celery.

Lo usan las tareas Celery (despliegue con Docker) y el ejecutor en proceso del modo local
(ARQ-08). Cada trabajo abre su propio engine/sesion con `contexto_tarea` (ARQ-07).
"""

import uuid
from typing import Any

import httpx

from app.integraciones.gemini.cliente import ClienteGeminiPerezoso
from app.integraciones.google_calendar.cliente import ClienteGoogleCalendar
from app.integraciones.whatsapp.cliente import ClienteWhatsApp
from app.repositorios import doctores as repo_doctores
from app.servicios import agenda, cierre, sync_google
from app.servicios.mensajes import manejar_mensaje
from app.worker import despacho
from app.worker.async_helper import contexto_tarea


async def procesar_mensaje(mensaje: dict[str, Any]) -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=30) as http:
        resultado = await manejar_mensaje(
            sesion=ctx.sesion,
            redis=ctx.redis,
            mensaje=mensaje,
            wa=ClienteWhatsApp(http),
            ia=ClienteGeminiPerezoso(),
        )
    if resultado is not None:
        for id_cita in resultado.citas_creadas:
            despacho.encolar_sync_google(id_cita)  # GC-01


async def sincronizar_cita(id_cita: uuid.UUID) -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=20) as http:
        await sync_google.sincronizar_cita(ctx.sesion, id_cita, ClienteGoogleCalendar(http))


async def marcar_error_sync(id_cita: uuid.UUID) -> None:
    async with contexto_tarea() as ctx:
        await sync_google.marcar_error(ctx.sesion, id_cita)


async def revisar_cierres() -> list[uuid.UUID]:
    async with contexto_tarea() as ctx:
        return await cierre.doctores_en_cierre(ctx.sesion, ctx.redis, agenda.ahora_utc())


async def enviar_resumen_cierre(id_doctor: uuid.UUID) -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=30) as http:
        doctor = await repo_doctores.obtener(ctx.sesion, id_doctor)
        if doctor is None or not doctor.activo:
            return
        await cierre.enviar_resumen_cierre(
            ctx.sesion, ctx.redis, ClienteWhatsApp(http), doctor, agenda.ahora_utc()
        )


async def enviar_recordatorios() -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=30) as http:
        await cierre.enviar_recordatorios_vencidos(
            ctx.sesion, ctx.redis, ClienteWhatsApp(http), agenda.ahora_utc()
        )
