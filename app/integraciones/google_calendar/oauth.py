"""OAuth2 de Google por doctor (GC-03)."""

import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import obtener_config
from app.core.seguridad import TokenInvalido, crear_token, decodificar_token

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
_TIPO_ESTADO = "google_oauth"


def url_autorizacion(id_doctor: uuid.UUID) -> str:
    cfg = obtener_config()
    estado = crear_token({"sub": str(id_doctor), "tipo": _TIPO_ESTADO}, minutos=10)
    parametros = {
        "client_id": cfg.google_client_id,
        "redirect_uri": cfg.google_redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": estado,
    }
    return f"{URL_AUTORIZACION}?{urlencode(parametros)}"


def doctor_de_estado(estado: str) -> uuid.UUID:
    datos = decodificar_token(estado)
    if datos.get("tipo") != _TIPO_ESTADO:
        raise TokenInvalido("Estado OAuth invalido")
    return uuid.UUID(datos["sub"])


def _credenciales(respuesta: dict[str, Any], refresh_previo: str | None = None) -> dict[str, Any]:
    return {
        "access_token": respuesta["access_token"],
        "refresh_token": respuesta.get("refresh_token") or refresh_previo,
        "expira_en": int(time.time()) + int(respuesta.get("expires_in", 3600)),
    }


async def intercambiar_codigo(http: httpx.AsyncClient, codigo: str) -> dict[str, Any]:
    cfg = obtener_config()
    respuesta = await http.post(
        URL_TOKEN,
        data={
            "code": codigo,
            "client_id": cfg.google_client_id,
            "client_secret": cfg.google_client_secret,
            "redirect_uri": cfg.google_redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    respuesta.raise_for_status()
    return _credenciales(respuesta.json())


async def refrescar(http: httpx.AsyncClient, credenciales: dict[str, Any]) -> dict[str, Any]:
    cfg = obtener_config()
    respuesta = await http.post(
        URL_TOKEN,
        data={
            "refresh_token": credenciales["refresh_token"],
            "client_id": cfg.google_client_id,
            "client_secret": cfg.google_client_secret,
            "grant_type": "refresh_token",
        },
    )
    respuesta.raise_for_status()
    return _credenciales(respuesta.json(), credenciales["refresh_token"])
