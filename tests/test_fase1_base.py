"""Fase 1: cifrado (SEG-01), logs sin PHI (SEG-02), auditoria (DAT-09), DAT-05."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cifrado
from app.core.config import obtener_config
from app.core.logging import REDACTADO, FiltroPHI, redactar
from app.modelos.cita import Cita
from app.modelos.enums import EstadoCita, OrigenCita
from app.modelos.log_auditoria import LogAuditoria
from app.repositorios import auditoria
from app.worker.async_helper import contexto_tarea, run_async
from tests.conftest import crear_doctor, crear_paciente

INICIO = datetime(2030, 1, 15, 17, 0, tzinfo=UTC)


def _cita(doctor, paciente, inicio=INICIO, minutos=30, **campos) -> Cita:
    return Cita(
        id_doctor=doctor.id,
        id_paciente=paciente.id,
        fecha_hora_inicio=inicio,
        fecha_hora_fin=inicio + timedelta(minutes=minutos),
        origen=OrigenCita.RECEPCION,
        **campos,
    )


def test_cifrado_ida_y_vuelta() -> None:
    token = cifrado.cifrar("dolor lumbar crónico")
    assert "lumbar" not in token
    assert cifrado.descifrar(token) == "dolor lumbar crónico"


def test_rotacion_de_llaves(monkeypatch: pytest.MonkeyPatch) -> None:
    vieja = obtener_config().fernet_keys
    token_viejo = cifrado.cifrar("dato")
    nueva = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEYS", f"{nueva},{vieja}")
    obtener_config.cache_clear()
    cifrado.obtener_fernet.cache_clear()
    try:
        assert cifrado.descifrar(token_viejo) == "dato"  # la llave vieja aun descifra
        assert Fernet(nueva.encode()).decrypt(cifrado.cifrar("x").encode()) == b"x"  # la 1a cifra
    finally:
        monkeypatch.setenv("FERNET_KEYS", vieja)
        obtener_config.cache_clear()
        cifrado.obtener_fernet.cache_clear()


def test_error_de_descifrado_no_filtra_contenido() -> None:
    with pytest.raises(cifrado.ErrorCifrado) as info:
        cifrado.descifrar("no-es-un-token")
    assert "no-es-un-token" not in str(info.value)


async def test_campos_medicos_cifrados_en_bd(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion, notas_clinicas_breves="alergia a penicilina")
    cita = _cita(doctor, paciente, motivo_consulta="revisión de rodilla")
    sesion.add(cita)
    await sesion.flush()
    crudo_nota = (
        await sesion.execute(
            text("SELECT notas_clinicas_breves FROM paciente WHERE id = :i"), {"i": paciente.id}
        )
    ).scalar_one()
    crudo_motivo = (
        await sesion.execute(text("SELECT motivo_consulta FROM cita WHERE id = :i"), {"i": cita.id})
    ).scalar_one()
    assert "penicilina" not in crudo_nota and "rodilla" not in crudo_motivo
    id_cita = cita.id
    sesion.expire_all()
    leida = (await sesion.execute(select(Cita).where(Cita.id == id_cita))).scalar_one()
    assert leida.motivo_consulta == "revisión de rodilla"


def test_redactar_estructuras() -> None:
    datos = {"id": 1, "motivo_consulta": "migraña", "anidado": [{"telefono": "+525512345678"}]}
    limpio = redactar(datos)
    assert limpio["id"] == 1
    assert limpio["motivo_consulta"] == REDACTADO
    assert limpio["anidado"][0]["telefono"] == REDACTADO


def test_filtro_de_logging_redacta(caplog: pytest.LogCaptureFixture) -> None:
    registro = logging.getLogger("prueba_phi")
    registro.addFilter(FiltroPHI())
    with caplog.at_level(logging.INFO, logger="prueba_phi"):
        registro.info("entrante de +525512345678 body='me duele la cabeza' motivo=migraña")
        registro.info("carga %s", {"texto": "paciente Ana", "tipo": "text"})
        registro.info("cabecera Authorization: Bearer abc.def-123")
    salida = caplog.text
    for secreto in ("5512345678", "duele", "migraña", "Ana", "abc.def-123"):
        assert secreto not in salida
    assert "'tipo': 'text'" in salida


async def test_auditoria_no_guarda_campos_cifrados(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion)
    await auditoria.registrar(
        sesion,
        entidad="cita",
        id_entidad=doctor.id,
        accion="crear",
        actor=auditoria.actor_ia(doctor.id),
        cambios={"motivo_consulta": "biopsia", "estado": EstadoCita.PROGRAMADA, "cuando": INICIO},
    )
    log = (await sesion.execute(select(LogAuditoria))).scalar_one()
    assert log.cambios["motivo_consulta"] == auditoria.MARCA_CIFRADO
    assert log.cambios["estado"] == "programada"
    assert log.actor == f"ia:{doctor.id}"


async def test_constraint_impide_solapamiento(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    sesion.add(_cita(doctor, paciente))
    await sesion.flush()
    with pytest.raises(IntegrityError, match="excl_cita_solapada"):
        async with sesion.begin_nested():
            sesion.add(_cita(doctor, paciente, INICIO + timedelta(minutes=15)))
            await sesion.flush()


async def test_constraint_permite_contiguas_canceladas_y_otro_doctor(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion)
    otro = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    sesion.add_all(
        [
            _cita(doctor, paciente, estado=EstadoCita.CANCELADA),
            _cita(doctor, paciente),  # mismo horario que la cancelada
            _cita(doctor, paciente, INICIO + timedelta(minutes=30)),  # contigua
            _cita(otro, paciente),  # otro doctor, mismo horario
            _cita(doctor, paciente, eliminado_en=INICIO),  # eliminada (soft delete)
        ]
    )
    await sesion.flush()


def test_run_async_usa_engine_propio() -> None:
    async def consulta() -> int:
        async with contexto_tarea() as ctx:
            return (await ctx.sesion.execute(text("SELECT 41 + 1"))).scalar_one()

    assert run_async(consulta()) == 42
    assert run_async(consulta()) == 42  # cada llamada: loop y engine nuevos
