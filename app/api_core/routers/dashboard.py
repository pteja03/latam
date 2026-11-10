"""KPIs del dashboard de recepcion (UI-03)."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.api_core.deps import Sesion, Usuario, filtrar_doctores
from app.esquemas.comunes import KpisSalida
from app.modelos.enums import EstadoCita
from app.repositorios import alertas as repo_alertas
from app.repositorios import citas as repo_citas
from app.repositorios import doctores as repo_doctores
from app.servicios import agenda

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis", response_model=KpisSalida)
async def kpis(sesion: Sesion, usuario: Usuario, id_doctor: uuid.UUID | None = None) -> KpisSalida:
    """ "Hoy" se calcula por doctor, en su propia zona horaria."""
    ids = filtrar_doctores(usuario, id_doctor)
    totales: dict[EstadoCita, int] = {}
    for doctor in await repo_doctores.listar(sesion, ids=ids):
        hoy = datetime.now(ZoneInfo(doctor.zona_horaria)).date()
        desde, hasta = agenda.limites_del_dia(hoy, doctor.zona_horaria)
        conteo = await repo_citas.contar_por_estado(
            sesion, ids_doctor=[doctor.id], desde=desde, hasta=hasta
        )
        for estado, total in conteo.items():
            totales[estado] = totales.get(estado, 0) + total
    return KpisSalida(
        citas_de_hoy=sum(t for e, t in totales.items() if e != EstadoCita.CANCELADA),
        en_espera=totales.get(EstadoCita.EN_ESPERA, 0),
        atendidos=totales.get(EstadoCita.ATENDIDA, 0),
        alertas_pendientes=await repo_alertas.contar_pendientes(sesion, ids),
    )
