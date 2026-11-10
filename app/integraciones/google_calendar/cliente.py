"""Cliente de Google Calendar (REST) con refresco automatico de token (GC-03)."""

import json
import time
from typing import Any

import httpx

from app.integraciones.google_calendar import oauth
from app.modelos.doctor import Doctor

URL_EVENTOS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_MARGEN_SEG = 60


class ClienteGoogleCalendar:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _cabeceras(self, doctor: Doctor) -> dict[str, str]:
        """Devuelve el Bearer vigente; si expiro lo refresca y lo guarda cifrado (DAT-01)."""
        assert doctor.credenciales_google_calendar is not None
        credenciales = json.loads(doctor.credenciales_google_calendar)
        if credenciales["expira_en"] - _MARGEN_SEG < time.time():
            credenciales = await oauth.refrescar(self._http, credenciales)
            doctor.credenciales_google_calendar = json.dumps(credenciales)
        return {"Authorization": f"Bearer {credenciales['access_token']}"}

    async def crear_evento(self, doctor: Doctor, evento: dict[str, Any]) -> str:
        respuesta = await self._http.post(
            URL_EVENTOS, headers=await self._cabeceras(doctor), json=evento
        )
        respuesta.raise_for_status()
        return respuesta.json()["id"]

    async def actualizar_evento(
        self, doctor: Doctor, id_evento: str, evento: dict[str, Any]
    ) -> None:
        respuesta = await self._http.patch(
            f"{URL_EVENTOS}/{id_evento}", headers=await self._cabeceras(doctor), json=evento
        )
        respuesta.raise_for_status()

    async def eliminar_evento(self, doctor: Doctor, id_evento: str) -> None:
        respuesta = await self._http.delete(
            f"{URL_EVENTOS}/{id_evento}", headers=await self._cabeceras(doctor)
        )
        if respuesta.status_code not in (404, 410):  # ya no existe: nada que borrar
            respuesta.raise_for_status()
