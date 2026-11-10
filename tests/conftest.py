"""Fixtures comunes. Los tests usan PostgreSQL real (DAT-05 no se puede probar en SQLite).

Gemini, Meta y Google se simulan siempre.
"""

import asyncio
import fnmatch
import os
import uuid
from collections.abc import AsyncIterator
from datetime import time
from typing import Any

from cryptography.fernet import Fernet

URL_BD_TEST = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/agenda_test"
)
os.environ.update(
    DATABASE_URL=URL_BD_TEST,
    FERNET_KEYS=Fernet.generate_key().decode(),
    JWT_SECRET="secreto-de-pruebas-con-longitud-suficiente-1234",
    WA_APP_SECRET="app-secret-de-pruebas",
    WA_VERIFY_TOKEN="verify-de-pruebas",
    WA_ACCESS_TOKEN="token-de-pruebas",
    WA_PHONE_NUMBER_ID="1234567890",
    GOOGLE_CLIENT_ID="cliente-google",
    GOOGLE_CLIENT_SECRET="secreto-google",
    GOOGLE_REDIRECT_URI="https://agenda.test/api/google/oauth/callback",
    GEMINI_MODEL="modelo-de-pruebas",
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.modelos  # noqa: E402, F401
from app.core.seguridad import crear_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.sesion import obtener_sesion  # noqa: E402
from app.modelos.doctor import Doctor  # noqa: E402
from app.modelos.enums import RolUsuario  # noqa: E402
from app.modelos.paciente import Paciente  # noqa: E402
from app.modelos.usuario_recepcion import UsuarioRecepcion  # noqa: E402
from app.servicios.pacientes import normalizar_nombre  # noqa: E402
from app.worker import despacho  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _esquema() -> None:
    async def crear() -> None:
        engine = create_async_engine(URL_BD_TEST, poolclass=NullPool)
        async with engine.begin() as conexion:
            await conexion.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
            await conexion.run_sync(Base.metadata.drop_all)
            await conexion.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(crear())


@pytest.fixture
async def sesion() -> AsyncIterator[AsyncSession]:
    """Sesion dentro de una transaccion externa que siempre se revierte."""
    engine = create_async_engine(URL_BD_TEST, poolclass=NullPool)
    async with engine.connect() as conexion:
        transaccion = await conexion.begin()
        async with AsyncSession(
            bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as s:
            yield s
        await transaccion.rollback()
    await engine.dispose()


class RedisFalso:
    """Subconjunto en memoria de redis.asyncio usado por la aplicacion."""

    def __init__(self) -> None:
        self.datos: dict[str, Any] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, clave: str, valor: Any, nx: bool = False, ex: int | None = None) -> bool:
        if nx and clave in self.datos:
            return False
        self.datos[clave] = valor
        if ex:
            self.ttl[clave] = ex
        return True

    async def get(self, clave: str) -> Any:
        return self.datos.get(clave)

    async def exists(self, clave: str) -> int:
        return int(clave in self.datos)

    async def delete(self, *claves: str) -> int:
        return sum(1 for c in claves if self.datos.pop(c, None) is not None)

    async def incr(self, clave: str) -> int:
        self.datos[clave] = int(self.datos.get(clave, 0)) + 1
        return self.datos[clave]

    async def expire(self, clave: str, segundos: int) -> bool:
        self.ttl[clave] = segundos
        return True

    async def rpush(self, clave: str, *valores: str) -> int:
        self.datos.setdefault(clave, []).extend(valores)
        return len(self.datos[clave])

    async def lrange(self, clave: str, inicio: int, fin: int) -> list[str]:
        lista = self.datos.get(clave, [])
        return lista[inicio:] if fin == -1 else lista[inicio : fin + 1]

    async def ltrim(self, clave: str, inicio: int, fin: int) -> bool:
        self.datos[clave] = await self.lrange(clave, inicio, fin)
        return True

    def claves(self, patron: str) -> list[str]:
        return fnmatch.filter(self.datos, patron)


@pytest.fixture
def redis() -> RedisFalso:
    return RedisFalso()


@pytest.fixture(autouse=True)
def sync_encoladas(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """Nunca se toca el broker: se registran las citas que se mandarian a Google."""
    encoladas: list[uuid.UUID] = []
    monkeypatch.setattr(despacho, "encolar_sync_google", encoladas.append)
    return encoladas


# ---------- fabricas ----------
async def crear_doctor(sesion: AsyncSession, **campos: Any) -> Doctor:
    datos: dict[str, Any] = {
        "nombre": "Dra. Elena Ruiz",
        "telefono_whatsapp": f"+5255{uuid.uuid4().int % 10**8:08d}",
        "zona_horaria": "America/Mexico_City",
        "hora_cierre_diario": time(20, 0),
    }
    doctor = Doctor(**{**datos, **campos})
    sesion.add(doctor)
    await sesion.flush()
    return doctor


async def crear_paciente(
    sesion: AsyncSession, nombre: str = "Ana López", **campos: Any
) -> Paciente:
    paciente = Paciente(
        nombre_completo=nombre, nombre_normalizado=normalizar_nombre(nombre), **campos
    )
    sesion.add(paciente)
    await sesion.flush()
    return paciente


async def crear_usuario(
    sesion: AsyncSession,
    rol: RolUsuario = RolUsuario.ADMIN,
    doctores: list[uuid.UUID] | None = None,
    password: str = "password-seguro",
) -> UsuarioRecepcion:
    usuario = UsuarioRecepcion(
        nombre="Recepcion",
        correo=f"{uuid.uuid4().hex[:10]}@cree.test",
        hash_password=hash_password(password),
        rol=rol,
        doctores_asignados=doctores or [],
    )
    sesion.add(usuario)
    await sesion.flush()
    return usuario


def cabeceras(usuario: UsuarioRecepcion) -> dict[str, str]:
    token = crear_token({"sub": str(usuario.id), "tipo": "acceso"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api(sesion: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    from app.api_core.main import app as api_core

    async def _sesion() -> AsyncIterator[AsyncSession]:
        yield sesion

    api_core.dependency_overrides[obtener_sesion] = _sesion
    transporte = httpx.ASGITransport(app=api_core)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test/api") as cliente:
        yield cliente
    api_core.dependency_overrides.clear()
