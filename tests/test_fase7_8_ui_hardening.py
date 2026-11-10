"""Fase 7: logica de la UI (zonas horarias, calendario). Fase 8: hardening de configuracion."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.core.config import Configuracion
from app.integraciones.gemini.cliente import ClienteGeminiPerezoso
from ui import componentes as comp
from ui import tema

DIA = date(2026, 11, 10)


def _cita(id_cita: str, id_doctor: str, inicio: str, fin: str, estado: str = "programada") -> dict:
    return {
        "id": id_cita,
        "id_doctor": id_doctor,
        "id_paciente": "p1",
        "paciente": {"id": "p1", "nombre_completo": "Ana López", "telefono": None},
        "fecha_hora_inicio": inicio,
        "fecha_hora_fin": fin,
        "motivo_consulta": None,
        "estado": estado,
        "estado_seguimiento": "ninguno",
        "origen": "ia",
    }


def test_horas_en_zona_del_doctor() -> None:
    cita = _cita("c1", "d1", "2026-11-10T23:00:00Z", "2026-11-10T23:30:00Z")
    assert comp.rango(cita, "America/Mexico_City") == "17:00 – 17:30"  # UI-08
    assert comp.rango(cita, "America/Tijuana") == "15:00 – 15:30"
    assert comp.abreviatura_zona("America/Mexico_City", DIA) == "Mexico City · UTC-6"
    assert comp.fecha_larga(DIA) == "Martes 10 de nov 2026"
    assert comp.iniciales("Dra. Elena Ruiz") == "DE" and comp.iniciales("ana") == "A"


def test_paleta_segun_spec() -> None:
    assert (tema.FONDO, tema.TARJETA, tema.PRIMARIO, tema.ACENTO, tema.TEXTO) == (
        "#F8FAFC",
        "#FFFFFF",
        "#0369A1",
        "#0F766E",
        "#1E293B",
    )  # UI-01
    assert set(tema.ESTADOS) == {
        "programada",
        "confirmada",
        "en_espera",
        "en_consulta",
        "atendida",
        "cancelada",
        "no_asistio",
    }


def _bloques(control) -> list:
    """Bloques de cita (contenedores con tooltip) dentro del arbol del calendario."""
    encontrados, pendientes = [], [control]
    while pendientes:
        actual = pendientes.pop()
        if getattr(actual, "tooltip", None):
            encontrados.append(actual)
        hijos = list(getattr(actual, "controls", None) or [])
        if getattr(actual, "content", None) is not None:
            hijos.append(actual.content)
        pendientes.extend(h for h in hijos if not isinstance(h, str))
    return encontrados


def test_calendario_ubica_cada_cita_en_la_columna_y_dia_local() -> None:
    doctores = [
        {"id": "d1", "nombre": "Dra. Ruiz", "zona_horaria": "America/Mexico_City"},
        {"id": "d2", "nombre": "Dra. Marín", "zona_horaria": "America/Tijuana"},
    ]
    citas = [
        _cita("c1", "d1", "2026-11-10T15:00:00Z", "2026-11-10T15:30:00Z"),  # 09:00 CDMX
        _cita("c2", "d2", "2026-11-10T17:00:00Z", "2026-11-10T18:00:00Z"),  # 09:00 Tijuana
        _cita("c3", "d1", "2026-11-11T05:30:00Z", "2026-11-11T06:00:00Z"),  # 23:30 del 10: fuera
        _cita("c4", "d1", "2026-11-11T15:00:00Z", "2026-11-11T15:30:00Z"),  # dia 11
        _cita("c5", "d1", "2026-11-10T16:00:00Z", "2026-11-10T16:30:00Z", "cancelada"),
    ]
    for intervalo in (15, 30):  # UI-07
        alto = comp.ALTO_INTERVALO[intervalo]
        bloques = {
            b.tooltip: b
            for b in _bloques(
                comp.calendario(doctores, citas, DIA, intervalo, lambda _: None, None)
            )
        }
        assert set(bloques) == {"Ana López · 09:00 – 09:30", "Ana López · 09:00 – 10:00"}
        media_hora, una_hora = (
            bloques["Ana López · 09:00 – 09:30"],
            bloques["Ana López · 09:00 – 10:00"],
        )
        # Ambas empiezan a las 09:00 de SU zona: misma altura en pantalla.
        assert media_hora.top == una_hora.top == 60 / intervalo * alto + 1
        assert una_hora.height == pytest.approx(60 / intervalo * alto - 3)


def test_produccion_exige_secretos_fuertes() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Configuracion(entorno="produccion", jwt_secret="corto", _env_file=None)
    with pytest.raises(ValidationError, match="FERNET_KEYS"):
        Configuracion(entorno="produccion", fernet_keys="", jwt_secret="x" * 40, _env_file=None)
    Configuracion(entorno="produccion", jwt_secret="x" * 40, _env_file=None)


async def test_cliente_gemini_no_se_crea_hasta_usarse(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import obtener_config

    cliente = ClienteGeminiPerezoso()  # sin llave: construir no falla
    monkeypatch.setattr(obtener_config(), "gemini_api_key", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await cliente.generar(sistema="", contenidos=[])
