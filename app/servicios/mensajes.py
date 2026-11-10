"""Procesamiento de un mensaje entrante de WhatsApp (WA-04, WA-05, IA-01..03, SEG-04)."""

import logging
import struct
import uuid
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obtener_config
from app.integraciones.gemini.cliente import ClienteIA
from app.integraciones.gemini.orquestador import EntradaDoctor, ResultadoIA, procesar_instruccion
from app.integraciones.whatsapp.cliente import Media, MediaDemasiadoGrande, candidatos_e164
from app.repositorios import doctores as repo_doctores

log = logging.getLogger(__name__)

TTL_VENTANA_SEG = 24 * 3600
MSJ_TIPO_NO_SOPORTADO = (
    "Por ahora solo puedo procesar mensajes de texto o notas de voz. ¿Me lo envías así, por favor?"
)
MSJ_AUDIO_LARGO = (
    "La nota de voz es demasiado larga. ¿Puedes dividirla en notas de menos de {minutos} minutos?"
)
MSJ_LIMITE = "Recibí muchos mensajes seguidos. Espera un minuto y vuelve a intentarlo."
MSJ_ERROR = "No pude procesar tu mensaje en este momento. Intenta de nuevo en unos minutos."


class Mensajeria(Protocol):
    async def enviar_texto(self, telefono: str, texto: str) -> None: ...
    async def descargar_media(self, media_id: str, max_bytes: int) -> Media: ...


def clave_ventana(id_doctor: uuid.UUID) -> str:
    """Existe mientras la ventana de 24 h de WhatsApp esta abierta (IA-18)."""
    return f"wa_ventana:{id_doctor}"


def duracion_ogg_segundos(datos: bytes) -> float | None:
    """Duracion de un OGG/Opus leyendo la posicion granular de la ultima pagina (48 kHz)."""
    posicion = datos.rfind(b"OggS")
    if posicion < 0 or posicion + 14 > len(datos):
        return None
    (granulo,) = struct.unpack_from("<q", datos, posicion + 6)
    return granulo / 48000 if granulo > 0 else None


async def _excede_limite(redis: Redis, id_doctor: uuid.UUID) -> bool:
    """SEG-04: ventana fija de 1 minuto por doctor."""
    clave = f"limite:{id_doctor}"
    total = await redis.incr(clave)
    if total == 1:
        await redis.expire(clave, 60)
    return total > obtener_config().limite_mensajes_por_minuto


async def manejar_mensaje(
    *,
    sesion: AsyncSession,
    redis: Redis,
    mensaje: dict[str, Any],
    wa: Mensajeria,
    ia: ClienteIA,
) -> ResultadoIA | None:
    """Devuelve el resultado de la IA, o None si el mensaje no llego a la IA."""
    cfg = obtener_config()
    remitente = str(mensaje.get("from", ""))
    doctor = await repo_doctores.obtener_por_telefonos(sesion, candidatos_e164(remitente))
    if doctor is None:
        log.info("Mensaje ignorado: remitente no registrado como doctor")  # WA-04
        return None

    await redis.set(clave_ventana(doctor.id), "1", ex=TTL_VENTANA_SEG)
    if await _excede_limite(redis, doctor.id):
        await wa.enviar_texto(remitente, MSJ_LIMITE)
        return None

    tipo = mensaje.get("type")
    if tipo == "text":
        entrada = EntradaDoctor(texto=str(mensaje.get("text", {}).get("body", "")))
    elif tipo == "audio":
        aviso_largo = MSJ_AUDIO_LARGO.format(minutos=cfg.audio_max_segundos // 60)
        try:
            media = await wa.descargar_media(mensaje["audio"]["id"], cfg.audio_max_bytes)
        except MediaDemasiadoGrande:
            await wa.enviar_texto(remitente, aviso_largo)  # IA-03
            return None
        duracion = duracion_ogg_segundos(media.datos)
        if duracion is not None and duracion > cfg.audio_max_segundos:
            await wa.enviar_texto(remitente, aviso_largo)
            return None
        entrada = EntradaDoctor(audio=media.datos, mime_audio=media.mime_type)
    else:
        await wa.enviar_texto(remitente, MSJ_TIPO_NO_SOPORTADO)  # WA-05
        return None

    try:
        resultado = await procesar_instruccion(
            sesion=sesion, redis=redis, doctor=doctor, entrada=entrada, ia=ia
        )
        await sesion.commit()
    except Exception as error:
        await sesion.rollback()
        # Solo el tipo de error: el mensaje de la excepcion podria contener PHI.
        log.error("Fallo al procesar instruccion: %s", type(error).__name__)
        await wa.enviar_texto(remitente, MSJ_ERROR)
        return None

    await wa.enviar_texto(remitente, resultado.respuesta)  # IA-13
    return resultado
