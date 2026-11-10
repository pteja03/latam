"""ARQ-01 api_core: CRUD, autenticacion de recepcion y endpoints que consume la UI."""

from fastapi import APIRouter, FastAPI

from app.api_core.routers import alertas, auth, citas, dashboard, doctores, google, pacientes
from app.core.config import obtener_config
from app.core.logging import configurar_logging

configurar_logging()
_produccion = obtener_config().entorno == "produccion"

app = FastAPI(
    title="Agenda Medica CREE - api_core",
    docs_url=None if _produccion else "/api/docs",
    redoc_url=None,
    openapi_url=None if _produccion else "/api/openapi.json",
)

api = APIRouter(prefix="/api")
for modulo in (auth, doctores, pacientes, citas, alertas, dashboard, google):
    api.include_router(modulo.router)
app.include_router(api)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"estado": "ok"}
