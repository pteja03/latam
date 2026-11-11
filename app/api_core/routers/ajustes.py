"""Ajustes de integraciones (UI-12) e instalacion inicial (UI-13)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api_core.deps import Admin, Sesion
from app.core.config import obtener_config
from app.core.seguridad import hash_password
from app.esquemas.comunes import UsuarioSalida
from app.modelos.enums import RolUsuario
from app.modelos.usuario_recepcion import UsuarioRecepcion
from app.repositorios import auditoria
from app.repositorios import usuarios as repo_usuarios
from app.servicios import ajustes as servicio

router = APIRouter(tags=["ajustes"])


class AjustesSalida(BaseModel):
    editable: bool
    valores: dict[str, str]
    secretos_configurados: dict[str, bool]
    url_webhook: str


class AjustesEntrada(BaseModel):
    """Solo se cambian los campos enviados. Un secreto vacio lo borra."""

    gemini_api_key: str | None = None
    gemini_model: str | None = None
    wa_access_token: str | None = None
    wa_phone_number_id: str | None = None
    wa_verify_token: str | None = None
    wa_app_secret: str | None = None
    wa_api_version: str | None = None
    wa_plantilla_cierre: str | None = None
    wa_plantilla_recordatorio: str | None = None
    wa_plantilla_idioma: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    url_publica: str | None = None
    tunel_token: str | None = None


class EstadoInstalacion(BaseModel):
    modo_local: bool
    requiere_admin: bool


class AdminInicial(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    correo: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)


@router.get("/ajustes", response_model=AjustesSalida)
async def leer_ajustes(_: Admin) -> dict[str, Any]:
    return servicio.leer()


@router.put("/ajustes", response_model=AjustesSalida)
async def guardar_ajustes(datos: AjustesEntrada, sesion: Sesion, admin: Admin) -> dict[str, Any]:
    cambios = datos.model_dump(exclude_unset=True)
    try:
        resultado = servicio.guardar(cambios)
    except servicio.AjustesNoEditables as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except servicio.ValorInvalido as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    # Se audita QUE ajustes cambiaron, nunca sus valores.
    await auditoria.registrar(
        sesion,
        entidad="ajustes",
        id_entidad=admin.id,
        accion="actualizar",
        actor=auditoria.actor_usuario(admin.id),
        cambios={"campos": sorted(cambios)},
    )
    return resultado


async def _sin_usuarios(sesion: Sesion) -> bool:
    consulta = (
        select(func.count())
        .select_from(UsuarioRecepcion)
        .where(UsuarioRecepcion.eliminado_en.is_(None))
    )
    return (await sesion.execute(consulta)).scalar_one() == 0


@router.get("/instalacion/estado", response_model=EstadoInstalacion)
async def estado_instalacion(sesion: Sesion) -> EstadoInstalacion:
    cfg = obtener_config()
    return EstadoInstalacion(
        modo_local=cfg.modo_local, requiere_admin=cfg.modo_local and await _sin_usuarios(sesion)
    )


@router.post(
    "/instalacion/admin", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED
)
async def crear_admin_inicial(datos: AdminInicial, sesion: Sesion) -> UsuarioRecepcion:
    """Primer arranque de la instalacion local: solo funciona mientras no exista ningun usuario."""
    if not obtener_config().modo_local or not await _sin_usuarios(sesion):
        raise HTTPException(status.HTTP_409_CONFLICT, "La instalacion ya tiene un administrador")
    if await repo_usuarios.obtener_por_correo(sesion, datos.correo):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo")
    usuario = UsuarioRecepcion(
        nombre=datos.nombre,
        correo=datos.correo.strip().lower(),
        hash_password=hash_password(datos.password),
        rol=RolUsuario.ADMIN,
    )
    sesion.add(usuario)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="usuario_recepcion",
        id_entidad=usuario.id,
        accion="crear",
        actor=auditoria.ACTOR_SISTEMA,
        cambios={"rol": RolUsuario.ADMIN, "origen": "instalacion"},
    )
    return usuario
