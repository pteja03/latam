"""Tarea Celery: procesa un mensaje de WhatsApp (IA, audio, respuesta)."""

from typing import Any

from app.worker import trabajos
from app.worker.async_helper import run_async
from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tareas_mensajes.procesar_mensaje")
def procesar_mensaje(mensaje: dict[str, Any]) -> None:
    run_async(trabajos.procesar_mensaje(mensaje))
