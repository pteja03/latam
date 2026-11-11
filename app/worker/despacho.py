"""Punto unico para encolar tareas desde servicios y routers.

Con Docker las tareas van a Celery. En modo local (ARQ-08) se ejecutan en proceso.
Los imports son perezosos para que api_core no cargue el worker al importar.
Un broker caido no debe tumbar la peticion: se registra y se sigue.
"""

import logging
import uuid
from typing import Any

from app.core.config import obtener_config

log = logging.getLogger(__name__)


def encolar_sync_google(id_cita: uuid.UUID) -> None:
    """GC-01: sincroniza la cita con Google Calendar en segundo plano."""
    try:
        if obtener_config().modo_local:
            from app.worker import local

            local.lanzar(local.sincronizar_con_reintentos(id_cita))
            return
        from app.worker.tareas_calendar import sincronizar_cita_google

        sincronizar_cita_google.delay(str(id_cita))
    except Exception:
        log.exception("No se pudo encolar la sincronizacion con Google Calendar")


def encolar_mensaje_whatsapp(mensaje: dict[str, Any]) -> None:
    """WA-06: el webhook solo encola; el procesamiento ocurre en segundo plano."""
    if obtener_config().modo_local:
        from app.worker import local, trabajos

        local.lanzar(trabajos.procesar_mensaje(mensaje))
        return
    from app.worker.tareas_mensajes import procesar_mensaje

    procesar_mensaje.delay(mensaje)
