"""Autenticacion de recepcion (SEG-03, UI-02) y gestion de usuarios (DAT-08)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.api_core.deps import Admin, Sesion, Usuario
from app.core.seguridad import crear_token, hash_password, verificar_password
from app.esquemas.comunes import (
    LoginEntrada,
    TokenSalida,
    UsuarioActualizar,
    UsuarioCrear,
    UsuarioSalida,
)
from app.modelos.usuario_recepcion import UsuarioRecepcion
from app.repositorios import auditoria
from app.repositorios import usuarios as repo

router = APIRouter(tags=["auth"])

# Hash de relleno: iguala el tiempo de respuesta cuando el correo no existe.
_HASH_RELLENO = hash_password("relleno-sin-uso")


@router.post("/auth/login", response_model=TokenSalida)
async def login(datos: LoginEntrada, sesion: Sesion) -> TokenSalida:
    usuario = await repo.obtener_por_correo(sesion, datos.correo)
    valido = verificar_password(datos.password, usuario.hash_password if usuario else _HASH_RELLENO)
    if usuario is None or not valido:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o password incorrectos")
    return TokenSalida(access_token=crear_token({"sub": str(usuario.id), "tipo": "acceso"}))


@router.get("/auth/yo", response_model=UsuarioSalida)
async def yo(usuario: Usuario) -> UsuarioRecepcion:
    return usuario


@router.get("/usuarios", response_model=list[UsuarioSalida])
async def listar_usuarios(sesion: Sesion, _: Admin) -> list[UsuarioRecepcion]:
    return await repo.listar(sesion)


@router.post("/usuarios", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
async def crear_usuario(datos: UsuarioCrear, sesion: Sesion, admin: Admin) -> UsuarioRecepcion:
    if await repo.obtener_por_correo(sesion, datos.correo):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    usuario = UsuarioRecepcion(
        nombre=datos.nombre,
        correo=datos.correo.strip().lower(),
        hash_password=hash_password(datos.password),
        rol=datos.rol,
        doctores_asignados=datos.doctores_asignados,
    )
    sesion.add(usuario)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="usuario_recepcion",
        id_entidad=usuario.id,
        accion="crear",
        actor=auditoria.actor_usuario(admin.id),
        cambios={"rol": datos.rol, "doctores_asignados": datos.doctores_asignados},
    )
    return usuario


@router.patch("/usuarios/{id_usuario}", response_model=UsuarioSalida)
async def actualizar_usuario(
    id_usuario: uuid.UUID, datos: UsuarioActualizar, sesion: Sesion, admin: Admin
) -> UsuarioRecepcion:
    usuario = await repo.obtener(sesion, id_usuario)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    if "password" in cambios:
        usuario.hash_password = hash_password(cambios["password"])
    for campo in ("nombre", "rol", "doctores_asignados"):
        if campo in cambios:
            setattr(usuario, campo, cambios[campo])
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="usuario_recepcion",
        id_entidad=usuario.id,
        accion="actualizar",
        actor=auditoria.actor_usuario(admin.id),
        cambios=cambios,
    )
    return usuario


@router.delete("/usuarios/{id_usuario}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_usuario(id_usuario: uuid.UUID, sesion: Sesion, admin: Admin) -> None:
    usuario = await repo.obtener(sesion, id_usuario)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if usuario.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes eliminar tu propio usuario")
    usuario.eliminado_en = datetime.now(UTC)
    await auditoria.registrar(
        sesion,
        entidad="usuario_recepcion",
        id_entidad=usuario.id,
        accion="eliminar",
        actor=auditoria.actor_usuario(admin.id),
    )
