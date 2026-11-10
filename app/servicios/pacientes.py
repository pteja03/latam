"""Logica de pacientes."""

import unicodedata
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.paciente import Paciente
from app.repositorios import auditoria
from app.repositorios import pacientes as repo


def normalizar_nombre(nombre: str) -> str:
    """Minusculas, sin acentos, espacios colapsados (DAT-02)."""
    descompuesto = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())


async def buscar(sesion: AsyncSession, nombre: str, limite: int = 20) -> list[Paciente]:
    palabras = normalizar_nombre(nombre).split()
    if not palabras:
        return []
    return await repo.buscar_por_nombre_normalizado(sesion, palabras, limite)


async def crear(sesion: AsyncSession, datos: dict[str, Any], actor: str) -> Paciente:
    paciente = Paciente(**datos, nombre_normalizado=normalizar_nombre(datos["nombre_completo"]))
    sesion.add(paciente)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="paciente",
        id_entidad=paciente.id,
        accion="crear",
        actor=actor,
        cambios=datos,
    )
    return paciente


async def actualizar(
    sesion: AsyncSession, paciente: Paciente, cambios: dict[str, Any], actor: str
) -> Paciente:
    for campo, valor in cambios.items():
        setattr(paciente, campo, valor)
    if "nombre_completo" in cambios:
        paciente.nombre_normalizado = normalizar_nombre(paciente.nombre_completo)
    await sesion.flush()
    await auditoria.registrar(
        sesion,
        entidad="paciente",
        id_entidad=paciente.id,
        accion="actualizar",
        actor=actor,
        cambios=cambios,
    )
    return paciente


async def obtener(sesion: AsyncSession, id_paciente: uuid.UUID) -> Paciente | None:
    return await repo.obtener(sesion, id_paciente)
