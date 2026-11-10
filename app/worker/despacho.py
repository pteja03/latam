"""Punto unico para encolar tareas Celery desde servicios y routers.

Los imports son perezosos para que api_core no cargue el worker al importar.
Un broker caido no debe tumbar la peticion: se registra y se sigue.
"""

import logging
import uuid
from typing import Any

log = logging.getLogger(__name__)


def encolar_sync_google(id_cita: uuid.UUID) -> None:
    """GC-01: sincroniza la cita con Google Calendar en el worker."""
    try:
        from app.worker.tareas_calendar import sincronizar_cita_google

        sincronizar_cita_google.delay(str(id_cita))
    except Exception:
        log.exception("No se pudo encolar la sincronizacion con Google Calendar")


def encolar_mensaje_whatsapp(mensaje: dict[str, Any]) -> None:
    """WA-06: el webhook solo encola; el worker procesa."""
    from app.worker.tareas_mensajes import procesar_mensaje

    procesar_mensaje.delay(mensaje)
