"""Ciclo de function calling por mensaje del doctor (IA-04, IA-05, IA-11..IA-14, IA-17)."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.genai import types
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import obtener_config
from app.integraciones.gemini.cliente import ClienteIA
from app.integraciones.gemini.ejecutor import EjecutorTools
from app.integraciones.gemini.prompt import construir_system_prompt
from app.modelos.doctor import Doctor
from app.repositorios import auditoria
from app.servicios import agenda, alertas

MARCA_NOTA_DE_VOZ = "[nota de voz]"
RESPUESTA_LIMITE = (
    "No pude completar tu instruccion de forma automatica. La pase a recepcion para que la "
    "atiendan."
)
RESPUESTA_VACIA = "No entendi la instruccion. ¿Puedes repetirla con mas detalle?"


@dataclass
class EntradaDoctor:
    texto: str | None = None
    audio: bytes | None = None
    mime_audio: str = "audio/ogg"


@dataclass
class ResultadoIA:
    respuesta: str
    citas_creadas: list[uuid.UUID] = field(default_factory=list)


def clave_historial(id_doctor: uuid.UUID) -> str:
    return f"chat:{id_doctor}"


def clave_cierre_pendiente(id_doctor: uuid.UUID) -> str:
    return f"cierre_pendiente:{id_doctor}"


async def cargar_historial(redis: Redis, id_doctor: uuid.UUID) -> list[dict[str, str]]:
    crudos = await redis.lrange(clave_historial(id_doctor), 0, -1)
    return [json.loads(c) for c in crudos]


async def guardar_turno(redis: Redis, id_doctor: uuid.UUID, usuario: str, modelo: str) -> None:
    """IA-04: ultimos N turnos por doctor, con TTL."""
    cfg = obtener_config()
    clave = clave_historial(id_doctor)
    await redis.rpush(
        clave,
        json.dumps({"rol": "user", "texto": usuario}),
        json.dumps({"rol": "model", "texto": modelo}),
    )
    await redis.ltrim(clave, -2 * cfg.ia_historial_turnos, -1)
    await redis.expire(clave, cfg.ia_historial_ttl_seg)


def _contenido_usuario(entrada: EntradaDoctor) -> types.Content:
    if entrada.audio is not None:
        # IA-02: el audio viaja inline, en memoria. No se persiste.
        partes = [
            types.Part.from_bytes(data=entrada.audio, mime_type=entrada.mime_audio),
            types.Part.from_text(text="Nota de voz del doctor. Interpretala como su instruccion."),
        ]
    else:
        partes = [types.Part.from_text(text=entrada.texto or "")]
    return types.Content(role="user", parts=partes)


async def procesar_instruccion(
    *,
    sesion: AsyncSession,
    redis: Redis,
    doctor: Doctor,
    entrada: EntradaDoctor,
    ia: ClienteIA,
) -> ResultadoIA:
    cfg = obtener_config()
    pregunta_cierre = await redis.get(clave_cierre_pendiente(doctor.id))
    sistema = construir_system_prompt(doctor, agenda.ahora_utc(), pregunta_cierre)

    contenidos: list[Any] = [
        types.Content(role=t["rol"], parts=[types.Part.from_text(text=t["texto"])])
        for t in await cargar_historial(redis, doctor.id)
    ]
    contenidos.append(_contenido_usuario(entrada))

    ejecutor = EjecutorTools(sesion, doctor)
    respuesta: str | None = None

    for _ in range(cfg.ia_max_iteraciones):
        salida = await ia.generar(sistema=sistema, contenidos=contenidos)
        if not salida.llamadas:
            respuesta = (salida.texto or "").strip() or RESPUESTA_VACIA
            break
        if salida.contenido is not None:
            contenidos.append(salida.contenido)
        resultados: list[types.Part] = []
        for llamada in salida.llamadas:
            if llamada.nombre == "solicitar_aclaracion":
                # IA-11: se responde al doctor y se espera su siguiente mensaje.
                respuesta = str(llamada.args.get("pregunta") or "").strip() or RESPUESTA_VACIA
                break
            resultado = await ejecutor.ejecutar(llamada.nombre, llamada.args)
            resultados.append(
                types.Part.from_function_response(name=llamada.nombre, response=resultado)
            )
        if respuesta is not None:
            break
        contenidos.append(types.Content(role="user", parts=resultados))
    else:
        # IA-14: limite alcanzado. Human-in-the-loop: recepcion lo resuelve.
        await alertas.crear(
            sesion,
            id_doctor=doctor.id,
            mensaje_ia="La IA alcanzo el limite de pasos sin completar la instruccion.",
            instruccion_original=entrada.texto or MARCA_NOTA_DE_VOZ,
            actor=auditoria.actor_ia(doctor.id),
        )
        respuesta = RESPUESTA_LIMITE

    assert respuesta is not None
    await guardar_turno(redis, doctor.id, entrada.texto or MARCA_NOTA_DE_VOZ, respuesta)
    if pregunta_cierre:
        await redis.delete(clave_cierre_pendiente(doctor.id))
    return ResultadoIA(respuesta=respuesta, citas_creadas=ejecutor.citas_creadas)
