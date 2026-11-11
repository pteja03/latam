"""Punto de entrada del ejecutable de Windows.

CreeAgenda.exe              abre la app de recepcion (y arranca el servidor si hace falta)
CreeAgenda.exe --servidor   solo el servidor local (se usa al iniciar sesion en Windows)
CreeAgenda.exe --detener    detiene el servidor local
"""

import os
import subprocess
import sys

from escritorio import configuracion, rutas


def _comando_servidor() -> list[str]:
    if rutas.congelado():
        return [sys.executable, "--servidor"]
    return [sys.executable, "-m", "escritorio.lanzador", "--servidor"]


def _arrancar_servidor_aparte() -> None:
    """Lanza el servidor como proceso independiente: sigue vivo al cerrar la ventana."""
    opciones: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(rutas.dir_instalacion()),
    }
    if os.name == "nt":
        opciones["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    else:
        opciones["start_new_session"] = True
    subprocess.Popen(_comando_servidor(), **opciones)  # noqa: S603


def _abrir_app() -> None:
    from escritorio import servidor

    valores = configuracion.asegurar()
    os.environ["API_CORE_URL"] = f"{servidor.url_api(valores)}/api"
    os.environ["CREE_MODO_LOCAL"] = "1"
    if not servidor.activo(valores):
        _arrancar_servidor_aparte()

    import flet as ft

    from ui.main import main as app_recepcion

    ft.run(app_recepcion)


def main() -> None:
    argumentos = sys.argv[1:]
    if "--servidor" in argumentos:
        from escritorio import servidor

        servidor.ejecutar()
    elif "--detener" in argumentos:
        from escritorio import servidor

        servidor.detener()
    else:
        _abrir_app()


if __name__ == "__main__":
    main()
