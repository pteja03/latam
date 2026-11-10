"""Aplicacion Celery (ARQ-03 worker, ARQ-04 beat)."""

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import obtener_config
from app.core.logging import configurar_logging

_cfg = obtener_config()

celery_app = Celery(
    "agenda_cree",
    broker=_cfg.redis_url,
    include=[
        "app.worker.tareas_mensajes",
        "app.worker.tareas_calendar",
        "app.worker.tareas_programadas",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # los mensajes llevan PHI: no se guardan resultados
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        # IA-15: cada 15 min revisa que doctores llegaron a su hora de cierre local.
        "revisar-cierres": {
            "task": "app.worker.tareas_programadas.revisar_cierres",
            "schedule": crontab(minute="*/15"),
        },
        # IA-18: recordatorios a su hora.
        "enviar-recordatorios": {
            "task": "app.worker.tareas_programadas.enviar_recordatorios",
            "schedule": 60.0,
        },
    },
)


@setup_logging.connect
def _configurar_logging(**_: object) -> None:
    configurar_logging()  # SEG-02: mismo filtro sin PHI en worker y beat
