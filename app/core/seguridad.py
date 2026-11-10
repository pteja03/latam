"""Hash de passwords (scrypt, stdlib) y tokens JWT (SEG-03)."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import obtener_config

_N, _R, _P = 2**14, 8, 1
ALGORITMO = "HS256"


class TokenInvalido(Exception):
    pass


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    derivado = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P)
    return f"scrypt${base64.b64encode(sal).decode()}${base64.b64encode(derivado).decode()}"


def verificar_password(password: str, hash_guardado: str) -> bool:
    try:
        _, sal_b64, derivado_b64 = hash_guardado.split("$")
        sal = base64.b64decode(sal_b64)
        esperado = base64.b64decode(derivado_b64)
    except ValueError:
        return False
    derivado = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P)
    return hmac.compare_digest(derivado, esperado)


def _secreto() -> str:
    secreto = obtener_config().jwt_secret
    if not secreto:
        raise RuntimeError("JWT_SECRET no esta configurado")
    return secreto


def crear_token(datos: dict[str, Any], minutos: int | None = None) -> str:
    cfg = obtener_config()
    expira = datetime.now(UTC) + timedelta(minutes=minutos or cfg.jwt_minutos_expiracion)
    return jwt.encode({**datos, "exp": expira}, _secreto(), algorithm=ALGORITMO)


def decodificar_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _secreto(), algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        raise TokenInvalido("Token invalido o expirado") from None
