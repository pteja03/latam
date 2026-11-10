"""Cliente de Gemini (SDK google-genai). El modelo sale de GEMINI_MODEL, nunca hardcodeado."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from google import genai
from google.genai import types

from app.core.config import obtener_config
from app.integraciones.gemini.tools import DECLARACIONES


@dataclass
class LlamadaTool:
    nombre: str
    args: dict[str, Any]


@dataclass
class RespuestaIA:
    texto: str | None = None
    llamadas: list[LlamadaTool] = field(default_factory=list)
    # Contenido original del modelo; se reenvia tal cual en el siguiente turno
    # (conserva las firmas de razonamiento que exigen los modelos recientes).
    contenido: Any = None


class ClienteIA(Protocol):
    async def generar(self, *, sistema: str, contenidos: list[Any]) -> RespuestaIA: ...


class ClienteGemini:
    def __init__(self) -> None:
        cfg = obtener_config()
        if not cfg.gemini_api_key or not cfg.gemini_model:
            raise RuntimeError("GEMINI_API_KEY y GEMINI_MODEL son obligatorios")
        self._modelo = cfg.gemini_model
        self._cliente = genai.Client(api_key=cfg.gemini_api_key)

    async def generar(self, *, sistema: str, contenidos: list[Any]) -> RespuestaIA:
        respuesta = await self._cliente.aio.models.generate_content(
            model=self._modelo,
            contents=contenidos,
            config=types.GenerateContentConfig(
                system_instruction=sistema,
                tools=[types.Tool(function_declarations=DECLARACIONES)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        llamadas = [
            LlamadaTool(nombre=fc.name or "", args=dict(fc.args or {}))
            for fc in (respuesta.function_calls or [])
        ]
        contenido = respuesta.candidates[0].content if respuesta.candidates else None
        texto = None if llamadas else respuesta.text
        return RespuestaIA(texto=texto, llamadas=llamadas, contenido=contenido)
