"""CRUD de pacientes (DAT-02). La busqueda usa nombre_normalizado."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api_core.deps import Sesion, Usuario
from app.esquemas.comunes import PacienteActualizar, PacienteCrear, PacienteResumen, PacienteSalida
from app.modelos.paciente import Paciente
from app.repositorios import auditoria
from app.servicios import pacientes as servicio

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


async def _obtener(sesion: Sesion, id_paciente: uuid.UUID) -> Paciente:
    paciente = await servicio.obtener(sesion, id_paciente)
    if paciente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return paciente


@router.get("", response_model=list[PacienteResumen])
async def buscar(
    sesion: Sesion, _: Usuario, q: str = Query(min_length=2, max_length=200)
) -> list[Paciente]:
    return await servicio.buscar(sesion, q)


@router.get("/{id_paciente}", response_model=PacienteSalida)
async def obtener(id_paciente: uuid.UUID, sesion: Sesion, _: Usuario) -> Paciente:
    return await _obtener(sesion, id_paciente)


@router.post("", response_model=PacienteSalida, status_code=status.HTTP_201_CREATED)
async def crear(datos: PacienteCrear, sesion: Sesion, usuario: Usuario) -> Paciente:
    return await servicio.crear(sesion, datos.model_dump(), auditoria.actor_usuario(usuario.id))


@router.patch("/{id_paciente}", response_model=PacienteSalida)
async def actualizar(
    id_paciente: uuid.UUID, datos: PacienteActualizar, sesion: Sesion, usuario: Usuario
) -> Paciente:
    paciente = await _obtener(sesion, id_paciente)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("nombre_completo", "x") is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nombre_completo es obligatorio")
    return await servicio.actualizar(sesion, paciente, cambios, auditoria.actor_usuario(usuario.id))


@router.delete("/{id_paciente}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(id_paciente: uuid.UUID, sesion: Sesion, usuario: Usuario) -> None:
    paciente = await _obtener(sesion, id_paciente)
    paciente.eliminado_en = datetime.now(UTC)
    await auditoria.registrar(
        sesion,
        entidad="paciente",
        id_entidad=paciente.id,
        accion="eliminar",
        actor=auditoria.actor_usuario(usuario.id),
    )
