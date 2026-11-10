"""CRUD de citas (DAT-03) con antisolapamiento (DAT-05)."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.api_core.deps import Sesion, Usuario, doctor_con_acceso, filtrar_doctores
from app.esquemas.comunes import CitaActualizar, CitaCrear, CitaSalida, HorarioOcupadoSalida
from app.modelos.cita import Cita
from app.modelos.enums import OrigenCita
from app.repositorios import auditoria
from app.repositorios import citas as repo
from app.servicios import agenda
from app.servicios import pacientes as servicio_pacientes
from app.worker import despacho

router = APIRouter(prefix="/citas", tags=["citas"])

_RESPUESTA_OCUPADO = {409: {"model": HorarioOcupadoSalida}}


def _ocupado(error: agenda.HorarioOcupado) -> JSONResponse:
    cuerpo = HorarioOcupadoSalida(alternativas=error.alternativas)
    return JSONResponse(cuerpo.model_dump(mode="json"), status.HTTP_409_CONFLICT)


async def _obtener(sesion: Sesion, usuario: Usuario, id_cita: uuid.UUID) -> Cita:
    cita = await repo.obtener(sesion, id_cita)
    if cita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    filtrar_doctores(usuario, cita.id_doctor)
    return cita


@router.get("", response_model=list[CitaSalida])
async def listar(
    sesion: Sesion,
    usuario: Usuario,
    id_doctor: uuid.UUID | None = None,
    desde: AwareDatetime | None = None,
    hasta: AwareDatetime | None = None,
) -> list[Cita]:
    ids = filtrar_doctores(usuario, id_doctor)
    return await repo.listar(sesion, ids_doctor=ids, desde=desde, hasta=hasta)


@router.get("/{id_cita}", response_model=CitaSalida)
async def obtener(id_cita: uuid.UUID, sesion: Sesion, usuario: Usuario) -> Cita:
    return await _obtener(sesion, usuario, id_cita)


@router.post(
    "",
    response_model=CitaSalida,
    status_code=status.HTTP_201_CREATED,
    responses=_RESPUESTA_OCUPADO,
)
async def crear(datos: CitaCrear, sesion: Sesion, usuario: Usuario) -> Cita | JSONResponse:
    doctor = await doctor_con_acceso(sesion, usuario, datos.id_doctor)
    if await servicio_pacientes.obtener(sesion, datos.id_paciente) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    fin = datos.fecha_hora_fin
    if fin is None and datos.duracion_minutos is not None:
        fin = datos.fecha_hora_inicio + timedelta(minutes=datos.duracion_minutos)
    try:
        cita = await agenda.crear_cita(
            sesion,
            doctor=doctor,
            id_paciente=datos.id_paciente,
            inicio=datos.fecha_hora_inicio,
            fin=fin,
            motivo=datos.motivo_consulta,
            origen=OrigenCita.RECEPCION,
            actor=auditoria.actor_usuario(usuario.id),
        )
    except agenda.HorarioOcupado as error:
        return _ocupado(error)
    await sesion.commit()
    despacho.encolar_sync_google(cita.id)
    return cita


@router.patch("/{id_cita}", response_model=CitaSalida, responses=_RESPUESTA_OCUPADO)
async def actualizar(
    id_cita: uuid.UUID, datos: CitaActualizar, sesion: Sesion, usuario: Usuario
) -> Cita | JSONResponse:
    cita = await _obtener(sesion, usuario, id_cita)
    doctor = await doctor_con_acceso(sesion, usuario, cita.id_doctor)
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("fecha_hora_inicio", "fecha_hora_fin", "estado", "estado_seguimiento"):
        if campo in cambios and cambios[campo] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{campo} no puede ser nulo")
    try:
        cita = await agenda.actualizar_cita(
            sesion,
            cita=cita,
            doctor=doctor,
            cambios=cambios,
            actor=auditoria.actor_usuario(usuario.id),
        )
    except agenda.HorarioOcupado as error:
        return _ocupado(error)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    await sesion.commit()
    despacho.encolar_sync_google(cita.id)
    return cita


@router.delete("/{id_cita}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(id_cita: uuid.UUID, sesion: Sesion, usuario: Usuario) -> None:
    cita = await _obtener(sesion, usuario, id_cita)
    await agenda.eliminar_cita(sesion, cita=cita, actor=auditoria.actor_usuario(usuario.id))
    await sesion.commit()
    despacho.encolar_sync_google(cita.id)
