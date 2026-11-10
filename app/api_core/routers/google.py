"""Conexion OAuth2 de Google Calendar por doctor (GC-03)."""

import json
import uuid

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse

from app.api_core.deps import Admin, Sesion, doctor_con_acceso
from app.core.seguridad import TokenInvalido
from app.integraciones.google_calendar import oauth
from app.repositorios import auditoria
from app.repositorios import doctores as repo_doctores

router = APIRouter(prefix="/google/oauth", tags=["google"])

_HTML_OK = """<!doctype html><html lang="es"><meta charset="utf-8">
<title>Clinica CREE</title>
<body style="font-family:system-ui;background:#F8FAFC;color:#1E293B;text-align:center;padding:4rem">
<h2 style="color:#0369A1">Google Calendar conectado</h2>
<p>Ya puedes cerrar esta ventana.</p></body></html>"""


@router.get("/iniciar")
async def iniciar(id_doctor: uuid.UUID, sesion: Sesion, admin: Admin) -> dict[str, str]:
    await doctor_con_acceso(sesion, admin, id_doctor)
    return {"url": oauth.url_autorizacion(id_doctor)}


@router.get("/callback", response_class=HTMLResponse)
async def callback(code: str, state: str, sesion: Sesion) -> str:
    """Google redirige aqui al navegador. Se autentica con el `state` firmado."""
    try:
        id_doctor = oauth.doctor_de_estado(state)
    except (TokenInvalido, KeyError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado OAuth invalido") from None
    doctor = await repo_doctores.obtener(sesion, id_doctor)
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor no encontrado")
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            credenciales = await oauth.intercambiar_codigo(http, code)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google rechazo la autorizacion") from None
    if not credenciales.get("refresh_token"):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google no entrego refresh token")
    doctor.credenciales_google_calendar = json.dumps(credenciales)
    await auditoria.registrar(
        sesion,
        entidad="doctor",
        id_entidad=doctor.id,
        accion="conectar_google_calendar",
        actor=auditoria.ACTOR_SISTEMA,
    )
    return _HTML_OK


@router.delete("/{id_doctor}", status_code=status.HTTP_204_NO_CONTENT)
async def desconectar(id_doctor: uuid.UUID, sesion: Sesion, admin: Admin) -> None:
    doctor = await doctor_con_acceso(sesion, admin, id_doctor)
    doctor.credenciales_google_calendar = None
    await auditoria.registrar(
        sesion,
        entidad="doctor",
        id_entidad=doctor.id,
        accion="desconectar_google_calendar",
        actor=auditoria.actor_usuario(admin.id),
    )
