"""Configuracion central leida de variables de entorno (pydantic-settings)."""

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    entorno: str = "desarrollo"
    # ARQ-08: instalacion "todo en una PC" (Windows). Sin Redis ni Celery: tareas en proceso.
    modo_local: bool = False
    puerto_api: int = 8765
    puerto_webhooks: int = 8766
    url_publica: str = ""  # direccion https publica que apunta al webhook (tunel)
    tunel_token: str = ""  # token de Cloudflare Tunnel (opcional)

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agenda"
    redis_url: str = "redis://localhost:6379/0"

    fernet_keys: str = ""
    jwt_secret: str = ""
    jwt_minutos_expiracion: int = 480

    gemini_api_key: str = ""
    gemini_model: str = ""

    wa_access_token: str = ""
    wa_phone_number_id: str = ""
    wa_verify_token: str = ""
    wa_app_secret: str = ""
    wa_api_version: str = "v23.0"
    wa_plantilla_cierre: str = "cierre_diario"
    wa_plantilla_recordatorio: str = "recordatorio_tarea"
    wa_plantilla_idioma: str = "es_MX"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Valores [DEFAULT] de SPEC
    ia_historial_turnos: int = 10  # IA-04
    ia_historial_ttl_seg: int = 7200  # IA-04
    ia_max_iteraciones: int = 5  # IA-14
    audio_max_segundos: int = 120  # IA-03
    audio_max_bytes: int = 5_000_000  # IA-03
    limite_mensajes_por_minuto: int = 20  # SEG-04
    jornada_hora_inicio: int = 8  # IA-07
    jornada_hora_fin: int = 20  # IA-07

    @model_validator(mode="after")
    def _exigir_secretos_en_produccion(self) -> "Configuracion":
        """En produccion el servicio no arranca con secretos vacios o debiles."""
        if self.entorno == "produccion":
            if not self.lista_fernet_keys:
                raise ValueError("FERNET_KEYS es obligatorio en produccion")
            if len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET debe tener al menos 32 caracteres en produccion")
        return self

    @property
    def lista_fernet_keys(self) -> list[str]:
        return [k.strip() for k in self.fernet_keys.split(",") if k.strip()]


VARIABLE_ARCHIVO_CONFIG = "CREE_ARCHIVO_CONFIG"


def ruta_archivo_config() -> str:
    """Archivo de configuracion: `.env` o el que indique CREE_ARCHIVO_CONFIG (modo local)."""
    return os.environ.get(VARIABLE_ARCHIVO_CONFIG, ".env")


@lru_cache
def obtener_config() -> Configuracion:
    return Configuracion(_env_file=ruta_archivo_config())
