"""CRUD de doctores (DAT-01). Escritura solo para admin."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api_core.deps import Admin, Sesion, Usuario, doctor_con_acceso, ids_doctor_permitidos
from app.esquemas.comunes import DoctorActualizar, DoctorCrear, DoctorSalida
from app.modelos.doctor import Doctor
from app.repositorios import auditoria
from app.repositorios import doctores as repo

router = APIRouter(prefix="/doctores", tags=["doctores"])

_TELEFONO_DUPLICADO = HTTPException(
    status.HTTP_409_CONFLICT, "Ya existe un doctor con ese telefono de WhatsApp"
)


def _salida(doctor: Doctor) -> DoctorSalida:
    salida = DoctorSalida.model_validate(doctor)
    salida.google_calendar_conectado = doctor.credenciales_google_calendar is not None
    return salida


@router.get("", response_model=list[DoctorSalida])
async def listar(sesion: Sesion, usuario: Usuario) -> list[DoctorSalida]:
    doctores = await repo.listar(sesion, ids=ids_doctor_permitidos(usuario))
    return [_salida(d) for d in doctores]


@router.get("/{id_doctor}", response_model=DoctorSalida)
async def obtener(id_doctor: uuid.UUID, sesion: Sesion, usuario: Usuario) -> DoctorSalida:
    return _salida(await doctor_con_acceso(sesion, usuario, id_doctor))


@router.post("", response_model=DoctorSalida, status_code=status.HTTP_201_CREATED)
async def crear(datos: DoctorCrear, sesion: Sesion, admin: Admin) -> DoctorSalida:
    doctor = Doctor(**datos.model_dump())
    try:
        async with sesion.begin_nested():
            sesion.add(doctor)
            await sesion.flush()
    except IntegrityError:
        raise _TELEFONO_DUPLICADO from None
    await auditoria.registrar(
        sesion,
        entidad="doctor",
        id_entidad=doctor.id,
        accion="crear",
        actor=auditoria.actor_usuario(admin.id),
        cambios=datos.model_dump(exclude={"nombre"}),
    )
    return _salida(doctor)


@router.patch("/{id_doctor}", response_model=DoctorSalida)
async def actualizar(
    id_doctor: uuid.UUID, datos: DoctorActualizar, sesion: Sesion, admin: Admin
) -> DoctorSalida:
    doctor = await doctor_con_acceso(sesion, admin, id_doctor)
    cambios = datos.model_dump(exclude_unset=True)
    try:
        async with sesion.begin_nested():
            for campo, valor in cambios.items():
                setattr(doctor, campo, valor)
            await sesion.flush()
    except IntegrityError:
        raise _TELEFONO_DUPLICADO from None
    await auditoria.registrar(
        sesion,
        entidad="doctor",
        id_entidad=doctor.id,
        accion="actualizar",
        actor=auditoria.actor_usuario(admin.id),
        cambios=cambios,
    )
    return _salida(doctor)


@router.delete("/{id_doctor}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(id_doctor: uuid.UUID, sesion: Sesion, admin: Admin) -> None:
    doctor = await doctor_con_acceso(sesion, admin, id_doctor)
    doctor.eliminado_en = datetime.now(UTC)
    doctor.activo = False
    await auditoria.registrar(
        sesion,
        entidad="doctor",
        id_entidad=doctor.id,
        accion="eliminar",
        actor=auditoria.actor_usuario(admin.id),
    )
