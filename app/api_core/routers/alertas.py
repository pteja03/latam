"""Bandeja de alertas IA para recepcion (DAT-07, UI-04)."""

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api_core.deps import Sesion, Usuario, filtrar_doctores
from app.esquemas.comunes import AlertaSalida
from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.enums import EstadoAlerta
from app.repositorios import alertas as repo
from app.servicios import alertas as servicio

router = APIRouter(prefix="/alertas", tags=["alertas"])


def _salida(alerta: AlertaRecepcion) -> AlertaSalida:
    return AlertaSalida(
        id=alerta.id,
        id_doctor=alerta.id_doctor,
        nombre_doctor=alerta.doctor.nombre,
        mensaje_ia=alerta.mensaje_ia,
        instruccion_original=alerta.instruccion_original,
        estado=alerta.estado,
        resuelta_por=alerta.resuelta_por,
        resuelta_en=alerta.resuelta_en,
        creado_en=alerta.creado_en,
    )


async def _obtener(sesion: Sesion, usuario: Usuario, id_alerta: uuid.UUID) -> AlertaRecepcion:
    alerta = await repo.obtener(sesion, id_alerta)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    filtrar_doctores(usuario, alerta.id_doctor)
    return alerta


@router.get("", response_model=list[AlertaSalida])
async def listar(
    sesion: Sesion,
    usuario: Usuario,
    id_doctor: uuid.UUID | None = None,
    estado: list[EstadoAlerta] | None = Query(default=None),
) -> list[AlertaSalida]:
    ids = filtrar_doctores(usuario, id_doctor)
    return [_salida(a) for a in await repo.listar(sesion, ids_doctor=ids, estados=estado)]


@router.post("/{id_alerta}/tomar", response_model=AlertaSalida)
async def tomar(id_alerta: uuid.UUID, sesion: Sesion, usuario: Usuario) -> AlertaSalida:
    alerta = await _obtener(sesion, usuario, id_alerta)
    try:
        await servicio.tomar(sesion, alerta, usuario.id)
    except servicio.TransicionInvalida as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _salida(alerta)


@router.post("/{id_alerta}/resolver", response_model=AlertaSalida)
async def resolver(id_alerta: uuid.UUID, sesion: Sesion, usuario: Usuario) -> AlertaSalida:
    alerta = await _obtener(sesion, usuario, id_alerta)
    try:
        await servicio.resolver(sesion, alerta, usuario.id)
    except servicio.TransicionInvalida as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _salida(alerta)
