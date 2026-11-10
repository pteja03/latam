"""Tarea Celery: procesa un mensaje de WhatsApp (IA, audio, respuesta)."""

from typing import Any

import httpx

from app.integraciones.gemini.cliente import ClienteGeminiPerezoso
from app.integraciones.whatsapp.cliente import ClienteWhatsApp
from app.servicios.mensajes import manejar_mensaje
from app.worker import despacho
from app.worker.async_helper import contexto_tarea, run_async
from app.worker.celery_app import celery_app


async def _procesar(mensaje: dict[str, Any]) -> None:
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


@celery_app.task(name="app.worker.tareas_mensajes.procesar_mensaje")
def procesar_mensaje(mensaje: dict[str, Any]) -> None:
    run_async(_procesar(mensaje))
