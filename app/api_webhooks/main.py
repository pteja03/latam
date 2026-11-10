"""ARQ-02 api_webhooks: recibe WhatsApp. Valida firma, deduplica, encola y responde 200.

Sin logica de negocio: todo lo pesado va a Celery (el webhook responde en < 1 s).
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis

from app.core.config import obtener_config
from app.core.logging import configurar_logging
from app.core.redis import crear_redis
from app.integraciones.whatsapp.firma import firma_valida
from app.worker import despacho

configurar_logging()
log = logging.getLogger(__name__)

TTL_IDEMPOTENCIA_SEG = 48 * 3600


@asynccontextmanager
async def _ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = crear_redis()
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title="Agenda Medica CREE - api_webhooks",
    lifespan=_ciclo_de_vida,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def obtener_redis(request: Request) -> Redis:
    return request.app.state.redis


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"estado": "ok"}


@app.get("/webhooks/whatsapp", response_class=PlainTextResponse)
async def verificar(
    modo: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    reto: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """WA-01: verificacion del webhook por Meta."""
    esperado = obtener_config().wa_verify_token
    if modo != "subscribe" or not esperado or token != esperado or reto is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verificacion rechazada")
    return reto


def _extraer_mensajes(carga: dict[str, Any]) -> list[dict[str, Any]]:
    mensajes: list[dict[str, Any]] = []
    for entrada in carga.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            mensajes.extend((cambio.get("value") or {}).get("messages") or [])
    return [m for m in mensajes if isinstance(m, dict) and m.get("id")]


@app.post("/webhooks/whatsapp")
async def recibir(
    request: Request, redis: Annotated[Redis, Depends(obtener_redis)]
) -> dict[str, str]:
    cuerpo = await request.body()
    firma = request.headers.get("X-Hub-Signature-256")
    if not firma_valida(cuerpo, firma, obtener_config().wa_app_secret):  # WA-02
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firma invalida")
    try:
        carga = json.loads(cuerpo)
    except ValueError:
        return {"estado": "ignorado"}
    for mensaje in _extraer_mensajes(carga if isinstance(carga, dict) else {}):
        # WA-03: Meta reintenta; cada message.id se procesa una sola vez.
        clave = f"wa_msg:{mensaje['id']}"
        if not await redis.set(clave, "1", nx=True, ex=TTL_IDEMPOTENCIA_SEG):
            continue
        try:
            despacho.encolar_mensaje_whatsapp(mensaje)  # WA-06
        except Exception:
            # Si no se pudo encolar, se libera la marca para que el reintento de Meta entre.
            await redis.delete(clave)
            log.error("No se pudo encolar un mensaje de WhatsApp")
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Cola no disponible") from None
    return {"estado": "ok"}
