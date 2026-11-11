"""Ajustes de integraciones editables desde la UI en la instalacion local (UI-12).

Se guardan en el archivo de configuracion (formato .env) que lee `Configuracion`. Los
secretos nunca se devuelven: solo se informa si estan configurados.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.core.config import obtener_config, ruta_archivo_config

# nombre del ajuste -> es secreto
CAMPOS: dict[str, bool] = {
    "gemini_api_key": True,
    "gemini_model": False,
    "wa_access_token": True,
    "wa_phone_number_id": False,
    "wa_verify_token": False,
    "wa_app_secret": True,
    "wa_api_version": False,
    "wa_plantilla_cierre": False,
    "wa_plantilla_recordatorio": False,
    "wa_plantilla_idioma": False,
    "google_client_id": False,
    "google_client_secret": True,
    "google_redirect_uri": False,
    "url_publica": False,
    "tunel_token": True,
}
_PROHIBIDOS = ("\n", "\r", "'", '"', "\\")

_al_cambiar: list[Callable[[], None]] = []


class AjustesNoEditables(Exception):
    pass


class ValorInvalido(Exception):
    pass


def suscribir_cambios(funcion: Callable[[], None]) -> None:
    """El servidor local se suscribe para reaccionar (por ejemplo, reiniciar el tunel)."""
    _al_cambiar.append(funcion)


def leer() -> dict[str, Any]:
    cfg = obtener_config()
    url = cfg.url_publica.rstrip("/")
    return {
        "editable": cfg.modo_local,
        "valores": {c: getattr(cfg, c) for c, secreto in CAMPOS.items() if not secreto},
        "secretos_configurados": {
            c: bool(getattr(cfg, c)) for c, secreto in CAMPOS.items() if secreto
        },
        "url_webhook": f"{url}/webhooks/whatsapp" if url else "",
    }


def escribir_archivo(ruta: Path, valores: dict[str, str]) -> None:
    lineas = [f"{clave}='{valor}'" for clave, valor in sorted(valores.items())]
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    temporal.replace(ruta)


def guardar(cambios: dict[str, str | None]) -> dict[str, Any]:
    """Aplica los cambios (None = no tocar) al archivo y recarga la configuracion."""
    if not obtener_config().modo_local:
        raise AjustesNoEditables("En este despliegue los ajustes se definen en el archivo .env")
    limpios: dict[str, str] = {}
    for campo, valor in cambios.items():
        if valor is None:
            continue
        if campo not in CAMPOS:
            raise ValorInvalido("Ajuste desconocido")
        valor = valor.strip()
        if any(c in valor for c in _PROHIBIDOS):
            raise ValorInvalido(
                "Los valores no pueden llevar comillas, barras invertidas ni saltos"
            )
        limpios[campo.upper()] = valor
    ruta = Path(ruta_archivo_config())
    actuales = {k: v or "" for k, v in dotenv_values(ruta).items()} if ruta.exists() else {}
    escribir_archivo(ruta, {**actuales, **limpios})
    obtener_config.cache_clear()
    for funcion in _al_cambiar:
        funcion()
    return leer()
