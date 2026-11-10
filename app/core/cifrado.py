"""Cifrado de campos medicos con MultiFernet (SEG-01).

La primera llave de FERNET_KEYS cifra; todas descifran (permite rotacion).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import obtener_config


class ErrorCifrado(Exception):
    """Error de cifrado. El mensaje nunca incluye el dato en claro."""


@lru_cache
def obtener_fernet() -> MultiFernet:
    llaves = obtener_config().lista_fernet_keys
    if not llaves:
        raise ErrorCifrado("FERNET_KEYS no esta configurado")
    return MultiFernet([Fernet(k.encode()) for k in llaves])


def cifrar(texto: str) -> str:
    return obtener_fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token: str) -> str:
    try:
        return obtener_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        # No se encadena la excepcion original para no filtrar contenido.
        raise ErrorCifrado("No se pudo descifrar el campo") from None
