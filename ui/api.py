"""Cliente HTTP de api_core. La UI nunca se conecta a la BD (ARQ-05)."""

import os
from typing import Any

import httpx

URL_API = os.environ.get("API_CORE_URL", "http://localhost:8000/api")


class ErrorApi(Exception):
    def __init__(self, estado: int, detalle: str, cuerpo: Any = None) -> None:
        super().__init__(detalle)
        self.estado = estado
        self.detalle = detalle
        self.cuerpo = cuerpo


class SesionExpirada(ErrorApi):
    pass


class ClienteApi:
    def __init__(self, url_base: str = URL_API) -> None:
        self._http = httpx.AsyncClient(base_url=url_base, timeout=15)
        self._token: str | None = None

    @property
    def autenticado(self) -> bool:
        return self._token is not None

    def cerrar_sesion(self) -> None:
        self._token = None

    async def _pedir(self, metodo: str, ruta: str, **kwargs: Any) -> Any:
        cabeceras = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            respuesta = await self._http.request(metodo, ruta, headers=cabeceras, **kwargs)
        except httpx.HTTPError:
            raise ErrorApi(0, "No se pudo conectar con el servidor") from None
        if respuesta.status_code == 204:
            return None
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = None
        if respuesta.is_success:
            return cuerpo
        detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else None
        if not isinstance(detalle, str):
            detalle = "Datos invalidos" if respuesta.status_code == 422 else "Error del servidor"
        if respuesta.status_code == 401 and self._token:
            self._token = None
            raise SesionExpirada(401, "La sesion expiro", cuerpo)
        raise ErrorApi(respuesta.status_code, detalle, cuerpo)

    # ---------- auth ----------
    async def login(self, correo: str, password: str) -> dict[str, Any]:
        datos = await self._pedir(
            "POST", "/auth/login", json={"correo": correo, "password": password}
        )
        self._token = datos["access_token"]
        return await self._pedir("GET", "/auth/yo")

    # ---------- lectura ----------
    async def doctores(self) -> list[dict[str, Any]]:
        return await self._pedir("GET", "/doctores")

    async def citas(self, desde: str, hasta: str) -> list[dict[str, Any]]:
        return await self._pedir("GET", "/citas", params={"desde": desde, "hasta": hasta})

    async def alertas(self) -> list[dict[str, Any]]:
        return await self._pedir("GET", "/alertas")

    async def kpis(self, id_doctor: str | None) -> dict[str, int]:
        parametros = {"id_doctor": id_doctor} if id_doctor else {}
        return await self._pedir("GET", "/dashboard/kpis", params=parametros)

    async def paciente(self, id_paciente: str) -> dict[str, Any]:
        return await self._pedir("GET", f"/pacientes/{id_paciente}")

    async def buscar_pacientes(self, nombre: str) -> list[dict[str, Any]]:
        return await self._pedir("GET", "/pacientes", params={"q": nombre})

    # ---------- escritura ----------
    async def crear_paciente(self, nombre: str, telefono: str | None) -> dict[str, Any]:
        cuerpo = {"nombre_completo": nombre, "telefono": telefono or None}
        return await self._pedir("POST", "/pacientes", json=cuerpo)

    async def crear_cita(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        return await self._pedir("POST", "/citas", json=cuerpo)

    async def cambiar_estado_cita(self, id_cita: str, estado: str) -> dict[str, Any]:
        return await self._pedir("PATCH", f"/citas/{id_cita}", json={"estado": estado})

    async def tomar_alerta(self, id_alerta: str) -> dict[str, Any]:
        return await self._pedir("POST", f"/alertas/{id_alerta}/tomar")

    async def resolver_alerta(self, id_alerta: str) -> dict[str, Any]:
        return await self._pedir("POST", f"/alertas/{id_alerta}/resolver")

    # ---------- instalacion y ajustes (UI-12, UI-13) ----------
    async def estado_instalacion(self) -> dict[str, bool]:
        return await self._pedir("GET", "/instalacion/estado")

    async def crear_admin_inicial(self, nombre: str, correo: str, password: str) -> dict[str, Any]:
        cuerpo = {"nombre": nombre, "correo": correo, "password": password}
        return await self._pedir("POST", "/instalacion/admin", json=cuerpo)

    async def ajustes(self) -> dict[str, Any]:
        return await self._pedir("GET", "/ajustes")

    async def guardar_ajustes(self, cambios: dict[str, str]) -> dict[str, Any]:
        return await self._pedir("PUT", "/ajustes", json=cambios)

    async def crear_doctor(self, datos: dict[str, Any]) -> dict[str, Any]:
        return await self._pedir("POST", "/doctores", json=datos)

    async def actualizar_doctor(self, id_doctor: str, datos: dict[str, Any]) -> dict[str, Any]:
        return await self._pedir("PATCH", f"/doctores/{id_doctor}", json=datos)

    async def url_google(self, id_doctor: str) -> str:
        datos = await self._pedir("GET", "/google/oauth/iniciar", params={"id_doctor": id_doctor})
        return datos["url"]

    async def usuarios(self) -> list[dict[str, Any]]:
        return await self._pedir("GET", "/usuarios")

    async def crear_usuario(self, datos: dict[str, Any]) -> dict[str, Any]:
        return await self._pedir("POST", "/usuarios", json=datos)
