"""PostgreSQL embebido: se inicializa y arranca con los binarios que trae el instalador."""

import os
import subprocess
from pathlib import Path

from escritorio.configuracion import NOMBRE_BD, USUARIO_BD

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ErrorPostgres(Exception):
    pass


class PostgresLocal:
    def __init__(self, dir_bin: Path, dir_datos: Path, registro: Path, puerto: int, clave: str):
        self._bin = dir_bin
        self._datos = dir_datos
        self._registro = registro
        self._puerto = puerto
        self._clave = clave

    def _exe(self, nombre: str) -> str:
        ruta = self._bin / (f"{nombre}.exe" if os.name == "nt" else nombre)
        if not ruta.exists():
            raise ErrorPostgres(f"No se encontro {ruta.name} en la instalacion")
        return str(ruta)

    def _correr(self, *args: str, capturar: bool = True) -> subprocess.CompletedProcess[str]:
        # Al arrancar el servidor no se capturan las salidas: el proceso hijo las heredaria
        # y la llamada no terminaria nunca.
        salida = subprocess.PIPE if capturar else subprocess.DEVNULL
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=salida,
            stderr=salida,
            text=True,
            env={**os.environ, "PGPASSWORD": self._clave},
            creationflags=_SIN_VENTANA,
            check=False,
        )

    def _exigir(self, resultado: subprocess.CompletedProcess[str], accion: str) -> None:
        if resultado.returncode != 0:
            raise ErrorPostgres(f"PostgreSQL no pudo {accion} (codigo {resultado.returncode})")

    def inicializar(self) -> None:
        """Crea el directorio de datos la primera vez."""
        if (self._datos / "PG_VERSION").exists():
            return
        self._datos.parent.mkdir(parents=True, exist_ok=True)
        archivo_clave = self._datos.parent / "clave_inicial.tmp"
        archivo_clave.write_text(self._clave, encoding="ascii")
        try:
            resultado = self._correr(
                self._exe("initdb"),
                "-D",
                str(self._datos),
                "-U",
                USUARIO_BD,
                "-A",
                "scram-sha-256",
                f"--pwfile={archivo_clave}",
                "-E",
                "UTF8",
                "--no-locale",
            )
            self._exigir(resultado, "inicializar la base de datos")
        finally:
            archivo_clave.unlink(missing_ok=True)

    def en_marcha(self) -> bool:
        return self._correr(self._exe("pg_ctl"), "-D", str(self._datos), "status").returncode == 0

    def iniciar(self) -> None:
        if self.en_marcha():
            return
        opciones = f"-p {self._puerto} -c listen_addresses=127.0.0.1"
        resultado = self._correr(
            self._exe("pg_ctl"),
            "-D",
            str(self._datos),
            "-l",
            str(self._registro),
            "-w",
            "-t",
            "90",
            "-o",
            opciones,
            "start",
            capturar=False,
        )
        self._exigir(resultado, "arrancar")

    def crear_base(self) -> None:
        conexion = ("-h", "127.0.0.1", "-p", str(self._puerto), "-U", USUARIO_BD)
        existe = self._correr(
            self._exe("psql"),
            *conexion,
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{NOMBRE_BD}'",
        )
        self._exigir(existe, "consultar las bases de datos")
        if existe.stdout.strip() != "1":
            self._exigir(self._correr(self._exe("createdb"), *conexion, NOMBRE_BD), "crear la base")

    def detener(self) -> None:
        if self.en_marcha():
            self._correr(self._exe("pg_ctl"), "-D", str(self._datos), "-m", "fast", "-w", "stop")
