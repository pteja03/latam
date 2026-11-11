"""Tarea Celery: sincroniza una cita con Google Calendar con reintentos y backoff (GC-02)."""

import logging
import uuid

from celery import Task

from app.worker.async_helper import run_async
from app.worker.celery_app import celery_app
from app.worker.trabajos import marcar_error_sync as _marcar_error
from app.worker.trabajos import sincronizar_cita as _sincronizar

log = logging.getLogger(__name__)

MAX_REINTENTOS = 5
BACKOFF_BASE_SEG = 30


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
