"""Ubicaciones de la instalacion local: programa (solo lectura) y datos del usuario."""

import os
import sys
from pathlib import Path

NOMBRE_APP = "CREE Agenda"


def congelado() -> bool:
    """True cuando corre como ejecutable empaquetado (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def dir_instalacion() -> Path:
    if congelado():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def dir_recursos() -> Path:
    """Donde quedan los archivos empaquetados junto al codigo (migraciones)."""
    return Path(getattr(sys, "_MEIPASS", dir_instalacion()))


def dir_datos() -> Path:
    """Datos de la clinica: base de datos, configuracion y registros. Nunca se desinstalan."""
    if os.environ.get("CREE_DIR_DATOS"):
        base = Path(os.environ["CREE_DIR_DATOS"])
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / NOMBRE_APP
    else:
        base = Path.home() / ".local" / "share" / "cree-agenda"
    base.mkdir(parents=True, exist_ok=True)
    return base


def dir_registros() -> Path:
    ruta = dir_datos() / "registros"
    ruta.mkdir(exist_ok=True)
    return ruta


def archivo_config() -> Path:
    return dir_datos() / "config.env"


def archivo_estado() -> Path:
    """PID del servidor y del tunel mientras estan en marcha."""
    return dir_datos() / "servidor.json"


def dir_postgres_bin() -> Path:
    if os.environ.get("CREE_DIR_POSTGRES"):
        return Path(os.environ["CREE_DIR_POSTGRES"])
    return dir_instalacion() / "postgres" / "bin"


def ejecutable_tunel() -> Path:
    return dir_instalacion() / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
