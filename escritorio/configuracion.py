"""Configuracion de la instalacion local. Se genera sola en el primer arranque."""

import os
import secrets

from cryptography.fernet import Fernet
from dotenv import dotenv_values

from app.core.config import VARIABLE_ARCHIVO_CONFIG, obtener_config
from app.servicios.ajustes import escribir_archivo
from escritorio import rutas

PUERTO_POSTGRES = 54329
USUARIO_BD = "agenda"
NOMBRE_BD = "agenda"


def _valores_iniciales() -> dict[str, str]:
    clave_bd = secrets.token_urlsafe(24)
    puerto_api = "8765"
    return {
        "MODO_LOCAL": "true",
        "ENTORNO": "produccion",
        "PUERTO_API": puerto_api,
        "PUERTO_WEBHOOKS": "8766",
        "PUERTO_POSTGRES": str(PUERTO_POSTGRES),
        "POSTGRES_PASSWORD": clave_bd,
        "DATABASE_URL": (
            f"postgresql+asyncpg://{USUARIO_BD}:{clave_bd}@127.0.0.1:{PUERTO_POSTGRES}/{NOMBRE_BD}"
        ),
        # Llave de cifrado de los datos medicos. Si se pierde, los datos no se pueden leer.
        "FERNET_KEYS": Fernet.generate_key().decode(),
        "JWT_SECRET": secrets.token_urlsafe(48),
        "WA_VERIFY_TOKEN": secrets.token_urlsafe(24),
        "GOOGLE_REDIRECT_URI": f"http://localhost:{puerto_api}/api/google/oauth/callback",
    }


def asegurar() -> dict[str, str]:
    """Crea config.env si no existe, lo activa para la aplicacion y devuelve sus valores."""
    ruta = rutas.archivo_config()
    if not ruta.exists():
        escribir_archivo(ruta, _valores_iniciales())
    os.environ[VARIABLE_ARCHIVO_CONFIG] = str(ruta)
    obtener_config.cache_clear()
    return {clave: valor or "" for clave, valor in dotenv_values(ruta).items()}
