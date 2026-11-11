"""ARQ-08 Ejecutor en proceso para la instalacion local (sin Celery ni Redis).

Las tareas corren como corrutinas en el mismo event loop del servidor local. Un
planificador sustituye a Celery Beat.
"""

import asyncio
import logging
import uuid
from collections.abc import Coroutine
from typing import Any

from app.worker import trabajos

log = logging.getLogger(__name__)

MAX_REINTENTOS_GOOGLE = 5
BACKOFF_BASE_SEG = 30
SEGUNDOS_RECORDATORIOS = 60
SEGUNDOS_CIERRES = 15 * 60

_en_curso: set[asyncio.Task[Any]] = set()


def _al_terminar(tarea: asyncio.Task[Any]) -> None:
    _en_curso.discard(tarea)
    if not tarea.cancelled() and tarea.exception() is not None:
        # Solo el tipo: el mensaje de la excepcion podria contener PHI.
        log.error("Tarea en segundo plano fallo: %s", type(tarea.exception()).__name__)


def lanzar(corrutina: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Programa la corrutina en el loop en curso y conserva la referencia hasta que termine."""
    tarea = asyncio.get_running_loop().create_task(corrutina)
    _en_curso.add(tarea)
    tarea.add_done_callback(_al_terminar)
    return tarea


async def sincronizar_con_reintentos(
    id_cita: uuid.UUID, base_seg: float = BACKOFF_BASE_SEG
) -> None:
    """GC-02: reintentos con backoff; al agotarlos, estado error y alerta a recepcion."""
    for intento in range(MAX_REINTENTOS_GOOGLE + 1):
        try:
            await trabajos.sincronizar_cita(id_cita)
            return
        except Exception as error:
            if intento == MAX_REINTENTOS_GOOGLE:
                log.error("Sincronizacion con Google agotada: %s", type(error).__name__)
                await trabajos.marcar_error_sync(id_cita)
                return
            await asyncio.sleep(base_seg * 2**intento)


async def ciclo_cierres() -> None:
    """IA-15: equivale a la tarea de Beat `revisar-cierres`."""
    for id_doctor in await trabajos.revisar_cierres():
        lanzar(trabajos.enviar_resumen_cierre(id_doctor))


async def planificador() -> None:
    """Sustituye a Celery Beat: recordatorios cada minuto y cierres cada 15 minutos."""
    transcurrido = SEGUNDOS_CIERRES  # primera revision de cierres al arrancar
    while True:
        try:
            await trabajos.enviar_recordatorios()
            if transcurrido >= SEGUNDOS_CIERRES:
                transcurrido = 0
                await ciclo_cierres()
        except Exception as error:
            log.error("Fallo en el planificador: %s", type(error).__name__)
        await asyncio.sleep(SEGUNDOS_RECORDATORIOS)
        transcurrido += SEGUNDOS_RECORDATORIOS
