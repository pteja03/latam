"""Dependencias de api_core: sesion, usuario autenticado (SEG-03) y control de acceso."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.seguridad import TokenInvalido, decodificar_token
from app.db.sesion import obtener_sesion
from app.modelos.doctor import Doctor
from app.modelos.enums import RolUsuario
from app.modelos.usuario_recepcion import UsuarioRecepcion
from app.repositorios import doctores as repo_doctores
from app.repositorios import usuarios as repo_usuarios

_bearer = HTTPBearer(auto_error=False)

# scope="function": la transaccion se confirma ANTES de enviar la respuesta. Sin esto, una
# peticion inmediata (crear cuenta y luego iniciar sesion) podia no ver lo recien guardado.
Sesion = Annotated[AsyncSession, Depends(obtener_sesion, scope="function")]


async def usuario_actual(
    sesion: Sesion,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UsuarioRecepcion:
    no_autorizado = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "No autenticado", {"WWW-Authenticate": "Bearer"}
    )
    if credenciales is None:
        raise no_autorizado
    try:
        datos = decodificar_token(credenciales.credentials)
        if datos.get("tipo") != "acceso":
            raise TokenInvalido
        id_usuario = uuid.UUID(datos["sub"])
    except (TokenInvalido, KeyError, ValueError):
        raise no_autorizado from None
    usuario = await repo_usuarios.obtener(sesion, id_usuario)
    if usuario is None:
        raise no_autorizado
    return usuario


Usuario = Annotated[UsuarioRecepcion, Depends(usuario_actual)]


async def requerir_admin(usuario: Usuario) -> UsuarioRecepcion:
    if usuario.rol != RolUsuario.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requiere rol admin")
    return usuario


Admin = Annotated[UsuarioRecepcion, Depends(requerir_admin)]


def ids_doctor_permitidos(usuario: UsuarioRecepcion) -> list[uuid.UUID] | None:
    """None = todos (admin). Recepcion solo ve sus doctores asignados."""
    return None if usuario.rol == RolUsuario.ADMIN else list(usuario.doctores_asignados)


def filtrar_doctores(
    usuario: UsuarioRecepcion, id_doctor: uuid.UUID | None
) -> list[uuid.UUID] | None:
    """Combina el filtro pedido con los doctores permitidos al usuario."""
    permitidos = ids_doctor_permitidos(usuario)
    if id_doctor is None:
        return permitidos
    if permitidos is not None and id_doctor not in permitidos:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a este doctor")
    return [id_doctor]


async def doctor_con_acceso(
    sesion: AsyncSession, usuario: UsuarioRecepcion, id_doctor: uuid.UUID
) -> Doctor:
    filtrar_doctores(usuario, id_doctor)
    doctor = await repo_doctores.obtener(sesion, id_doctor)
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor no encontrado")
    return doctor
