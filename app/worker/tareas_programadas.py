"""Tareas de Celery Beat: cierre nocturno (IA-15..17) y recordatorios (IA-18)."""

import uuid

import httpx

from app.worker import trabajos
from app.worker.async_helper import run_async
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tareas_programadas.revisar_cierres")
def revisar_cierres() -> None:
    for id_doctor in run_async(trabajos.revisar_cierres()):
        enviar_resumen_cierre.delay(str(id_doctor))


@celery_app.task(
    name="app.worker.tareas_programadas.enviar_resumen_cierre",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=30,
    max_retries=3,
)
def enviar_resumen_cierre(id_doctor: str) -> None:
    run_async(trabajos.enviar_resumen_cierre(uuid.UUID(id_doctor)))


@celery_app.task(name="app.worker.tareas_programadas.enviar_recordatorios")
def enviar_recordatorios() -> None:
    run_async(trabajos.enviar_recordatorios())
