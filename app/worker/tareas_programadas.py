"""Tareas de Celery Beat: cierre nocturno (IA-15..17) y recordatorios (IA-18)."""

import uuid

import httpx

from app.integraciones.whatsapp.cliente import ClienteWhatsApp
from app.repositorios import doctores as repo_doctores
from app.servicios import agenda, cierre
from app.worker.async_helper import contexto_tarea, run_async
from app.worker.celery_app import celery_app


async def _revisar_cierres() -> list[uuid.UUID]:
    async with contexto_tarea() as ctx:
        return await cierre.doctores_en_cierre(ctx.sesion, ctx.redis, agenda.ahora_utc())


@celery_app.task(name="app.worker.tareas_programadas.revisar_cierres")
def revisar_cierres() -> None:
    for id_doctor in run_async(_revisar_cierres()):
        enviar_resumen_cierre.delay(str(id_doctor))


async def _enviar_resumen(id_doctor: uuid.UUID) -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=30) as http:
        doctor = await repo_doctores.obtener(ctx.sesion, id_doctor)
        if doctor is None or not doctor.activo:
            return
        await cierre.enviar_resumen_cierre(
            ctx.sesion, ctx.redis, ClienteWhatsApp(http), doctor, agenda.ahora_utc()
        )


@celery_app.task(
    name="app.worker.tareas_programadas.enviar_resumen_cierre",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=30,
    max_retries=3,
)
def enviar_resumen_cierre(id_doctor: str) -> None:
    run_async(_enviar_resumen(uuid.UUID(id_doctor)))


async def _enviar_recordatorios() -> None:
    async with contexto_tarea() as ctx, httpx.AsyncClient(timeout=30) as http:
        await cierre.enviar_recordatorios_vencidos(
            ctx.sesion, ctx.redis, ClienteWhatsApp(http), agenda.ahora_utc()
        )


@celery_app.task(name="app.worker.tareas_programadas.enviar_recordatorios")
def enviar_recordatorios() -> None:
    run_async(_enviar_recordatorios())
