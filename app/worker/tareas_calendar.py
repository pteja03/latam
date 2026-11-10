"""Tarea Celery: sincroniza una cita con Google Calendar con reintentos y backoff (GC-02)."""

import logging
import uuid

import httpx
from celery import Task

from app.integraciones.google_calendar.cliente import ClienteGoogleCalendar
from app.servicios import sync_google
from app.worker.async_helper import contexto_tarea, run_async
from app.worker.celery_app import celery_app

log = logging.getLogger(__name__)

MAX_REINTENTOS = 5
BACKOFF_BASE_SEG = 30


async def _sincronizar(id_cita: uuid.UUID) -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=20) as http:
        await sync_google.sincronizar_cita(ctx.sesion, id_cita, ClienteGoogleCalendar(http))


async def _marcar_error(id_cita: uuid.UUID) -> None:
    async with contexto_tarea() as ctx:
        await sync_google.marcar_error(ctx.sesion, id_cita)


@celery_app.task(
    bind=True, name="app.worker.tareas_calendar.sincronizar_cita_google", max_retries=MAX_REINTENTOS
)
def sincronizar_cita_google(self: Task, id_cita: str) -> None:
    try:
        run_async(_sincronizar(uuid.UUID(id_cita)))
    except Exception as error:
        if self.request.retries >= MAX_REINTENTOS:
            log.error("Sincronizacion con Google agotada: %s", type(error).__name__)
            run_async(_marcar_error(uuid.UUID(id_cita)))
            return
        raise self.retry(exc=error, countdown=BACKOFF_BASE_SEG * 2**self.request.retries) from None
