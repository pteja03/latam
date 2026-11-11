"""Servidor local: PostgreSQL, api_core, webhook, planificador y tunel en un solo proceso."""

import asyncio
import json
import logging
import os
import signal
import subprocess
import urllib.request
from logging.handlers import RotatingFileHandler

import uvicorn
from alembic import command
from alembic.config import Config

from app.core.config import obtener_config
from app.core.logging import FiltroPHI
from escritorio import configuracion, rutas
from escritorio.postgres import PostgresLocal

log = logging.getLogger("escritorio.servidor")

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _configurar_registro() -> None:
    manejador = RotatingFileHandler(
        rutas.dir_registros() / "servidor.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    manejador.addFilter(FiltroPHI())  # SEG-02
    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(logging.INFO)


def url_api(valores: dict[str, str]) -> str:
    return f"http://127.0.0.1:{valores.get('PUERTO_API', '8765')}"


def activo(valores: dict[str, str]) -> bool:
    try:
        with urllib.request.urlopen(f"{url_api(valores)}/health", timeout=2) as respuesta:
            return respuesta.status == 200
    except OSError:
        return False


def _postgres(valores: dict[str, str]) -> PostgresLocal:
    return PostgresLocal(
        dir_bin=rutas.dir_postgres_bin(),
        dir_datos=rutas.dir_datos() / "pgdata",
        registro=rutas.dir_registros() / "postgres.log",
        puerto=int(valores["PUERTO_POSTGRES"]),
        clave=valores["POSTGRES_PASSWORD"],
    )


def _migrar() -> None:
    """Aplica las migraciones Alembic empaquetadas. Debe llamarse fuera de un event loop."""
    cfg = Config()
    cfg.set_main_option("script_location", str(rutas.dir_recursos() / "migrations"))
    command.upgrade(cfg, "head")


class Tunel:
    """Cloudflare Tunnel: da al webhook la direccion https publica que exige Meta."""

    def __init__(self) -> None:
        self._proceso: subprocess.Popen[bytes] | None = None
        self._token = ""

    @property
    def pid(self) -> int | None:
        return self._proceso.pid if self._proceso else None

    def sincronizar(self) -> None:
        """Arranca, reinicia o detiene el tunel segun el token configurado."""
        token = obtener_config().tunel_token
        if token == self._token and (not token or self._vivo()):
            return
        self.detener()
        self._token = token
        ejecutable = rutas.ejecutable_tunel()
        if not token or not ejecutable.exists():
            return
        self._proceso = subprocess.Popen(  # noqa: S603
            [str(ejecutable), "tunnel", "--no-autoupdate", "run"],
            env={**os.environ, "TUNNEL_TOKEN": token},  # el token no viaja en la linea de comandos
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_SIN_VENTANA,
        )
        log.info("Tunel iniciado")
        _guardar_estado(self.pid)

    def _vivo(self) -> bool:
        return self._proceso is not None and self._proceso.poll() is None

    def detener(self) -> None:
        if self._vivo():
            assert self._proceso is not None
            self._proceso.terminate()
        self._proceso = None


def _guardar_estado(pid_tunel: int | None) -> None:
    rutas.archivo_estado().write_text(
        json.dumps({"pid": os.getpid(), "pid_tunel": pid_tunel}), encoding="ascii"
    )


async def _servir(tunel: Tunel) -> None:
    # Imports tardios: la configuracion ya apunta al archivo local.
    from app.api_core.main import app as api_core
    from app.api_webhooks.main import app as api_webhooks
    from app.servicios import ajustes
    from app.worker import local

    _configurar_registro()  # las apps configuran su propio logging al importarse
    cfg = obtener_config()
    servidores = [
        uvicorn.Server(uvicorn.Config(aplicacion, host="127.0.0.1", port=puerto, log_config=None))
        for aplicacion, puerto in ((api_core, cfg.puerto_api), (api_webhooks, cfg.puerto_webhooks))
    ]

    async def vigilar() -> None:
        """Si un servidor se detiene, se detienen los dos. Tambien revisa el tunel."""
        while not any(s.should_exit for s in servidores):
            await asyncio.sleep(1)
            tunel.sincronizar()
        for servidor in servidores:
            servidor.should_exit = True

    ajustes.suscribir_cambios(tunel.sincronizar)
    tunel.sincronizar()
    planificador = local.lanzar(local.planificador())
    try:
        await asyncio.gather(vigilar(), *(s.serve() for s in servidores))
    finally:
        planificador.cancel()


def ejecutar() -> None:
    valores = configuracion.asegurar()
    _configurar_registro()
    if activo(valores):
        return  # ya hay un servidor en marcha
    postgres = _postgres(valores)
    tunel = Tunel()
    try:
        postgres.inicializar()
        postgres.iniciar()
        postgres.crear_base()
        _migrar()
        _configurar_registro()  # Alembic puede haber cambiado los manejadores
        _guardar_estado(None)
        log.info("Servidor local iniciado")
        asyncio.run(_servir(tunel))
    except Exception:
        log.exception("El servidor local se detuvo por un error")
        raise
    finally:
        tunel.detener()
        postgres.detener()
        rutas.archivo_estado().unlink(missing_ok=True)


def _terminar(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def detener() -> None:
    """Detiene servidor, tunel y PostgreSQL (lo usa el desinstalador)."""
    valores = configuracion.asegurar()
    ruta = rutas.archivo_estado()
    if ruta.exists():
        try:
            estado = json.loads(ruta.read_text(encoding="ascii"))
        except ValueError:
            estado = {}
        _terminar(estado.get("pid_tunel"))
        _terminar(estado.get("pid"))
        ruta.unlink(missing_ok=True)
    try:
        _postgres(valores).detener()
    except Exception:
        log.warning("No se pudo detener PostgreSQL")
