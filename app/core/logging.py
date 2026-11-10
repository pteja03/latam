"""Logging sin PHI (SEG-02): redacta campos sensibles y contenido de mensajes."""

import logging
import re
from typing import Any

CAMPOS_SENSIBLES = frozenset(
    {
        "motivo_consulta",
        "notas_clinicas_breves",
        "credenciales_google_calendar",
        "instruccion_original",
        "instruccion_literal",
        "mensaje_ia",
        "descripcion",
        "descripcion_tarea",
        "motivo",
        "texto",
        "body",
        "mensaje",
        "nombre_completo",
        "nombre_paciente_nuevo",
        "telefono",
        "correo",
        "password",
        "hash_password",
        "access_token",
        "refresh_token",
        "authorization",
    }
)
REDACTADO = "[REDACTADO]"

_CLAVES = "|".join(sorted(CAMPOS_SENSIBLES))
_PATRON_CLAVE_VALOR = re.compile(
    rf"""(?P<pre>["']?\b(?:{_CLAVES})\b["']?\s*[:=]\s*)(?P<val>"[^"]*"|'[^']*'|[^,;}}\s]+)""",
    re.IGNORECASE,
)
_PATRON_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_PATRON_TELEFONO = re.compile(r"\+?\d{10,15}\b")


def redactar_texto(texto: str) -> str:
    # El Bearer va primero: si no, "Authorization: Bearer x" dejaria el token a la vista.
    texto = _PATRON_BEARER.sub(r"\1" + REDACTADO, texto)
    texto = _PATRON_CLAVE_VALOR.sub(lambda m: m.group("pre") + REDACTADO, texto)
    return _PATRON_TELEFONO.sub(REDACTADO, texto)


def redactar(valor: Any) -> Any:
    """Redacta recursivamente dicts/listas; las claves sensibles pierden su valor."""
    if isinstance(valor, dict):
        return {
            k: REDACTADO if str(k).lower() in CAMPOS_SENSIBLES else redactar(v)
            for k, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        return type(valor)(redactar(v) for v in valor)
    if isinstance(valor, str):
        return redactar_texto(valor)
    return valor


class FiltroPHI(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = redactar(record.args)
        elif record.args:
            record.args = tuple(redactar(a) for a in record.args)
        if isinstance(record.msg, str):
            record.msg = redactar_texto(record.msg)
        return True


def configurar_logging(nivel: int = logging.INFO) -> None:
    manejador = logging.StreamHandler()
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    manejador.addFilter(FiltroPHI())
    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(nivel)
