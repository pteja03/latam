"""ARQ-08 Instalacion local: almacen sobre PostgreSQL, tareas en proceso, ajustes e instalacion."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import dotenv_values
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.almacen_local import AlmacenLocal
from app.core.config import VARIABLE_ARCHIVO_CONFIG, obtener_config
from app.modelos.log_auditoria import LogAuditoria
from app.servicios import ajustes
from app.worker import despacho, local, trabajos
from tests.conftest import URL_BD_TEST, cabeceras, crear_usuario


@pytest.fixture
def config_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Activa el modo local con un archivo de configuracion temporal."""
    archivo = tmp_path / "config.env"
    ajustes.escribir_archivo(archivo, {"MODO_LOCAL": "true", "WA_PLANTILLA_IDIOMA": "es_MX"})
    monkeypatch.setenv(VARIABLE_ARCHIVO_CONFIG, str(archivo))
    obtener_config.cache_clear()
    yield archivo
    monkeypatch.delenv(VARIABLE_ARCHIVO_CONFIG)
    obtener_config.cache_clear()


@pytest.fixture
async def almacen() -> AsyncIterator[AlmacenLocal]:
    engine: AsyncEngine = create_async_engine(URL_BD_TEST, poolclass=NullPool)
    async with engine.begin() as conexion:
        await conexion.execute(text("TRUNCATE almacen_clave_valor"))
    yield AlmacenLocal(engine)
    async with engine.begin() as conexion:
        await conexion.execute(text("TRUNCATE almacen_clave_valor"))
    await engine.dispose()


async def _vencer(almacen: AlmacenLocal, clave: str) -> None:
    async with almacen._engine.begin() as conexion:
        await conexion.execute(
            text(
                "UPDATE almacen_clave_valor SET expira_en = now() - interval '1 second' "
                "WHERE clave = :c"
            ),
            {"c": clave},
        )


# ---------- almacen (sustituto de Redis) ----------
async def test_almacen_set_nx_y_caducidad(almacen: AlmacenLocal) -> None:
    assert await almacen.set("wa_msg:1", "1", nx=True, ex=60) is True
    assert await almacen.set("wa_msg:1", "1", nx=True, ex=60) is False  # idempotencia (WA-03)
    assert await almacen.exists("wa_msg:1") == 1
    await _vencer(almacen, "wa_msg:1")
    assert await almacen.get("wa_msg:1") is None and await almacen.exists("wa_msg:1") == 0
    assert await almacen.set("wa_msg:1", "2", nx=True, ex=60) is True  # vencida: se puede retomar
    assert await almacen.get("wa_msg:1") == "2"
    assert await almacen.set("wa_msg:1", "3") is True  # sin nx sobrescribe
    assert await almacen.get("wa_msg:1") == "3"
    assert await almacen.delete("wa_msg:1", "no-existe") == 1


async def test_almacen_contador_y_listas(almacen: AlmacenLocal) -> None:
    assert [await almacen.incr("limite:d") for _ in range(3)] == [1, 2, 3]
    assert await almacen.expire("limite:d", 60) is True
    await _vencer(almacen, "limite:d")
    assert await almacen.incr("limite:d") == 1  # ventana nueva tras vencer

    for i in range(4):
        await almacen.rpush("chat:d", f"u{i}", f"m{i}")
    await almacen.ltrim("chat:d", -4, -1)
    assert await almacen.lrange("chat:d", 0, -1) == ["u2", "m2", "u3", "m3"]
    assert await almacen.lrange("vacia", 0, -1) == []
    await _vencer(almacen, "limite:d")
    assert await almacen.purgar_vencidas() == 1


async def test_almacen_guarda_cifrado(almacen: AlmacenLocal) -> None:
    await almacen.rpush("chat:d", "Agenda a Ana López mañana")
    async with almacen._engine.connect() as conexion:
        crudo = (await conexion.execute(text("SELECT valor FROM almacen_clave_valor"))).scalar_one()
    assert "Ana" not in crudo


async def test_almacen_incr_concurrente(almacen: AlmacenLocal) -> None:
    await asyncio.gather(*(almacen.incr("contador") for _ in range(8)))
    assert await almacen.get("contador") == 8


def test_crear_redis_en_modo_local(config_local: Path) -> None:
    from app.core.redis import crear_redis

    assert isinstance(crear_redis(), AlmacenLocal)


# ---------- tareas en proceso (sustituto de Celery) ----------
async def test_despacho_local_procesa_en_proceso(
    config_local: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recibidos: list[dict[str, Any]] = []

    async def procesar(mensaje: dict[str, Any]) -> None:
        recibidos.append(mensaje)

    monkeypatch.setattr(trabajos, "procesar_mensaje", procesar)
    despacho.encolar_mensaje_whatsapp({"id": "wamid.1"})
    await asyncio.gather(*local._en_curso)
    assert recibidos == [{"id": "wamid.1"}]
    await asyncio.sleep(0)
    assert not local._en_curso  # no se acumulan referencias


async def test_sync_local_reintenta_y_marca_error(monkeypatch: pytest.MonkeyPatch) -> None:
    intentos: list[uuid.UUID] = []
    marcadas: list[uuid.UUID] = []

    async def falla(id_cita: uuid.UUID) -> None:
        intentos.append(id_cita)
        raise httpx.ConnectError("google caido")

    async def marcar(id_cita: uuid.UUID) -> None:
        marcadas.append(id_cita)

    monkeypatch.setattr(trabajos, "sincronizar_cita", falla)
    monkeypatch.setattr(trabajos, "marcar_error_sync", marcar)
    id_cita = uuid.uuid4()
    await local.sincronizar_con_reintentos(id_cita, base_seg=0)
    assert len(intentos) == local.MAX_REINTENTOS_GOOGLE + 1 and marcadas == [id_cita]  # GC-02


async def test_ciclo_de_cierres_lanza_un_resumen_por_doctor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doctores = [uuid.uuid4(), uuid.uuid4()]
    enviados: list[uuid.UUID] = []

    async def revisar() -> list[uuid.UUID]:
        return doctores

    async def resumen(id_doctor: uuid.UUID) -> None:
        enviados.append(id_doctor)

    monkeypatch.setattr(trabajos, "revisar_cierres", revisar)
    monkeypatch.setattr(trabajos, "enviar_resumen_cierre", resumen)
    await local.ciclo_cierres()
    await asyncio.gather(*local._en_curso)
    assert enviados == doctores


async def test_fallo_en_tarea_no_registra_el_mensaje(caplog: pytest.LogCaptureFixture) -> None:
    async def rota() -> None:
        raise RuntimeError("datos de la paciente Ana López")

    tarea = local.lanzar(rota())
    await asyncio.gather(tarea, return_exceptions=True)
    await asyncio.sleep(0)
    assert "RuntimeError" in caplog.text and "Ana" not in caplog.text


# ---------- ajustes (UI-12) ----------
async def test_ajustes_guardar_y_leer(
    api: httpx.AsyncClient, sesion: AsyncSession, config_local: Path
) -> None:
    admin = await crear_usuario(sesion)
    avisos: list[int] = []
    ajustes.suscribir_cambios(lambda: avisos.append(1))
    cuerpo = {
        "gemini_api_key": "llave-gemini-secreta",
        "wa_api_version": " v24.0 ",
        "url_publica": "https://agenda.clinica.mx/",
    }
    guardado = await api.put("/ajustes", json=cuerpo, headers=cabeceras(admin))
    assert guardado.status_code == 200, guardado.text
    datos = guardado.json()
    assert datos["editable"] is True
    assert datos["valores"]["wa_api_version"] == "v24.0"
    assert datos["secretos_configurados"]["gemini_api_key"] is True
    assert datos["secretos_configurados"]["wa_app_secret"] is True  # viene del entorno de pruebas
    assert datos["url_webhook"] == "https://agenda.clinica.mx/webhooks/whatsapp"
    assert "llave-gemini-secreta" not in guardado.text  # los secretos nunca se devuelven
    assert avisos == [1]
    # Se aplica sin reiniciar y queda en el archivo, sin tocar lo que ya habia.
    assert obtener_config().gemini_api_key == "llave-gemini-secreta"
    archivo = dotenv_values(config_local)
    assert archivo["GEMINI_API_KEY"] == "llave-gemini-secreta" and archivo["MODO_LOCAL"] == "true"
    # La auditoria registra que campos cambiaron, no sus valores.
    log = await sesion.execute(select(LogAuditoria).where(LogAuditoria.entidad == "ajustes"))
    cambios = log.scalar_one().cambios
    assert cambios == {"campos": ["gemini_api_key", "url_publica", "wa_api_version"]}
    leido = await api.get("/ajustes", headers=cabeceras(admin))
    assert leido.json() == datos


async def test_ajustes_validaciones_y_permisos(
    api: httpx.AsyncClient, sesion: AsyncSession, config_local: Path
) -> None:
    from app.modelos.enums import RolUsuario

    admin = await crear_usuario(sesion)
    recepcion = await crear_usuario(sesion, RolUsuario.RECEPCION)
    assert (await api.get("/ajustes")).status_code == 401
    assert (await api.get("/ajustes", headers=cabeceras(recepcion))).status_code == 403
    for malo in ("con'comilla", "dos\nlineas", 'con"doble'):
        respuesta = await api.put(
            "/ajustes", json={"wa_api_version": malo}, headers=cabeceras(admin)
        )
        assert respuesta.status_code == 422
    assert dotenv_values(config_local).get("WA_API_VERSION") is None


async def test_ajustes_no_editables_fuera_del_modo_local(
    api: httpx.AsyncClient, sesion: AsyncSession
) -> None:
    admin = await crear_usuario(sesion)
    leido = await api.get("/ajustes", headers=cabeceras(admin))
    assert leido.json()["editable"] is False
    cambio = await api.put("/ajustes", json={"gemini_model": "x"}, headers=cabeceras(admin))
    assert cambio.status_code == 409


# ---------- instalacion inicial (UI-13) ----------
async def test_instalacion_crea_un_unico_admin(
    api: httpx.AsyncClient, sesion: AsyncSession, config_local: Path
) -> None:
    assert (await api.get("/instalacion/estado")).json() == {
        "modo_local": True,
        "requiere_admin": True,
    }
    datos = {"nombre": "Laura", "correo": "Laura@Cree.mx", "password": "clave-segura-1"}
    corta = await api.post("/instalacion/admin", json={**datos, "password": "corta"})
    assert corta.status_code == 422
    creado = await api.post("/instalacion/admin", json=datos)
    assert creado.status_code == 201 and creado.json()["rol"] == "admin"
    assert (await api.post("/instalacion/admin", json=datos)).status_code == 409
    assert (await api.get("/instalacion/estado")).json()["requiere_admin"] is False
    login = await api.post(
        "/auth/login", json={"correo": "laura@cree.mx", "password": "clave-segura-1"}
    )
    assert login.status_code == 200


async def test_instalacion_cerrada_fuera_del_modo_local(api: httpx.AsyncClient) -> None:
    assert (await api.get("/instalacion/estado")).json() == {
        "modo_local": False,
        "requiere_admin": False,
    }
    datos = {"nombre": "X", "correo": "x@cree.mx", "password": "clave-segura-1"}
    assert (await api.post("/instalacion/admin", json=datos)).status_code == 409
