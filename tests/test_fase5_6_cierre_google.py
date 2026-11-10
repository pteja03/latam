"""Fase 5: cierre nocturno y recordatorios (IA-15..18). Fase 6: Google Calendar (GC-*)."""

import json
import time as reloj
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integraciones.gemini.orquestador import clave_cierre_pendiente
from app.integraciones.google_calendar import oauth
from app.integraciones.google_calendar.cliente import ClienteGoogleCalendar
from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.cita import Cita
from app.modelos.enums import EstadoCita, EstadoRecordatorio, EstadoSyncGoogle, OrigenCita
from app.modelos.recordatorio import Recordatorio
from app.servicios import cierre, sync_google
from app.servicios.mensajes import clave_ventana
from tests.conftest import RedisFalso, cabeceras, crear_doctor, crear_paciente, crear_usuario
from tests.test_fase3_whatsapp_ia import WAFalso

AHORA = datetime(2030, 3, 5, 2, 30, tzinfo=UTC)  # 4 mar 20:30 en Ciudad de Mexico (UTC-6)


async def _cita(sesion, doctor, paciente, inicio, **campos) -> Cita:
    cita = Cita(
        id_doctor=doctor.id,
        id_paciente=paciente.id,
        fecha_hora_inicio=inicio,
        fecha_hora_fin=inicio + timedelta(minutes=30),
        origen=OrigenCita.RECEPCION,
        **campos,
    )
    sesion.add(cita)
    await sesion.flush()
    return cita


# ---------- cierre nocturno ----------
async def test_cierre_respeta_hora_local_y_no_repite(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    ya_cerro = await crear_doctor(sesion, hora_cierre_diario=time(20, 0))
    aun_no = await crear_doctor(sesion, hora_cierre_diario=time(21, 0))
    otra_zona = await crear_doctor(  # en Tijuana son las 18:30
        sesion, hora_cierre_diario=time(20, 0), zona_horaria="America/Tijuana"
    )
    await crear_doctor(sesion, hora_cierre_diario=time(8, 0), activo=False)
    assert await cierre.doctores_en_cierre(sesion, redis, AHORA) == [ya_cerro.id]
    # 15 min despues: no se repite el del mismo dia.
    assert await cierre.doctores_en_cierre(sesion, redis, AHORA + timedelta(minutes=15)) == []
    mas_tarde = await cierre.doctores_en_cierre(sesion, redis, AHORA + timedelta(hours=2))
    assert set(mas_tarde) == {aun_no.id, otra_zona.id}
    # Al dia siguiente vuelve a tocar.
    assert ya_cerro.id in await cierre.doctores_en_cierre(sesion, redis, AHORA + timedelta(days=1))


async def test_resumen_de_cierre_usa_plantilla_y_guarda_contexto(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    hoy_10 = datetime(2030, 3, 4, 16, 0, tzinfo=UTC)  # 4 mar 10:00 local
    await _cita(sesion, doctor, paciente, hoy_10, estado=EstadoCita.ATENDIDA)
    await _cita(sesion, doctor, paciente, hoy_10 + timedelta(hours=1), estado=EstadoCita.ATENDIDA)
    await _cita(sesion, doctor, paciente, hoy_10 + timedelta(hours=2))  # sin cerrar
    await _cita(sesion, doctor, paciente, hoy_10 + timedelta(hours=3), estado=EstadoCita.CANCELADA)
    await _cita(sesion, doctor, paciente, hoy_10 + timedelta(days=1))  # manana
    wa = WAFalso()
    await cierre.enviar_resumen_cierre(sesion, redis, wa, doctor, AHORA)
    assert wa.enviados == []  # IA-16: nunca texto libre
    assert wa.plantillas == [
        (doctor.telefono_whatsapp, "cierre_diario", [doctor.nombre, "2", "1", "1"])
    ]
    pregunta = await redis.get(clave_cierre_pendiente(doctor.id))  # IA-17
    assert "2 citas atendidas" in pregunta and "pendientes" in pregunta


# ---------- recordatorios ----------
async def test_recordatorios_texto_o_plantilla_segun_ventana(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    con_ventana = await crear_doctor(sesion)
    sin_ventana = await crear_doctor(sesion)
    await redis.set(clave_ventana(con_ventana.id), "1")
    vencido_1 = Recordatorio(
        id_doctor=con_ventana.id, fecha_hora=AHORA - timedelta(minutes=1), descripcion="Llamar lab"
    )
    vencido_2 = Recordatorio(
        id_doctor=sin_ventana.id, fecha_hora=AHORA, descripcion="Firmar receta"
    )
    futuro = Recordatorio(
        id_doctor=con_ventana.id, fecha_hora=AHORA + timedelta(hours=1), descripcion="Despues"
    )
    sesion.add_all([vencido_1, vencido_2, futuro])
    await sesion.flush()
    wa = WAFalso()
    assert await cierre.enviar_recordatorios_vencidos(sesion, redis, wa, AHORA) == 2
    assert wa.enviados == [(con_ventana.telefono_whatsapp, "Recordatorio: Llamar lab")]
    assert wa.plantillas == [
        (sin_ventana.telefono_whatsapp, "recordatorio_tarea", ["Firmar receta"])
    ]
    assert vencido_1.estado == vencido_2.estado == EstadoRecordatorio.ENVIADO
    assert futuro.estado == EstadoRecordatorio.PENDIENTE
    # No se reenvian.
    assert await cierre.enviar_recordatorios_vencidos(sesion, redis, wa, AHORA) == 0


async def test_recordatorio_con_fallo_de_envio_queda_pendiente(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    recordatorio = Recordatorio(id_doctor=doctor.id, fecha_hora=AHORA, descripcion="x")
    sesion.add(recordatorio)
    await sesion.flush()

    class WARoto(WAFalso):
        async def enviar_plantilla(self, *_: Any) -> None:
            raise httpx.ConnectError("sin red")

    assert await cierre.enviar_recordatorios_vencidos(sesion, redis, WARoto(), AHORA) == 0
    assert recordatorio.estado == EstadoRecordatorio.PENDIENTE


# ---------- Google Calendar ----------
class CalendarioFalso:
    def __init__(self, falla: bool = False) -> None:
        self.operaciones: list[tuple[str, Any]] = []
        self._falla = falla

    async def crear_evento(self, doctor, evento) -> str:
        if self._falla:
            raise httpx.ConnectError("google caido")
        self.operaciones.append(("crear", evento))
        return "evento-1"

    async def actualizar_evento(self, doctor, id_evento, evento) -> None:
        self.operaciones.append(("actualizar", id_evento))

    async def eliminar_evento(self, doctor, id_evento) -> None:
        self.operaciones.append(("eliminar", id_evento))


def _credenciales(expira_en_seg: int = 3600) -> str:
    return json.dumps(
        {
            "access_token": "acc-1",
            "refresh_token": "ref-1",
            "expira_en": int(reloj.time()) + expira_en_seg,
        }
    )


async def test_sync_crea_actualiza_y_borra_evento(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion, credenciales_google_calendar=_credenciales())
    paciente = await crear_paciente(sesion, "Ana López")
    cita = await _cita(sesion, doctor, paciente, AHORA, motivo_consulta="biopsia de piel")
    calendario = CalendarioFalso()

    await sync_google.sincronizar_cita(sesion, cita.id, calendario)
    _, evento = calendario.operaciones[0]
    assert evento["summary"] == "Consulta - Ana López"
    assert "biopsia" not in json.dumps(evento)  # GC-01: sin datos clinicos
    assert set(evento) == {"summary", "start", "end"}
    assert cita.id_evento_google == "evento-1"
    assert cita.estado_sync_google == EstadoSyncGoogle.SINCRONIZADO

    await sync_google.sincronizar_cita(sesion, cita.id, calendario)
    cita.estado = EstadoCita.CANCELADA
    await sesion.flush()
    await sync_google.sincronizar_cita(sesion, cita.id, calendario)
    assert [op for op, _ in calendario.operaciones] == ["crear", "actualizar", "eliminar"]
    assert cita.id_evento_google is None


async def test_sync_borra_evento_de_cita_eliminada(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion, credenciales_google_calendar=_credenciales())
    paciente = await crear_paciente(sesion)
    cita = await _cita(
        sesion, doctor, paciente, AHORA, id_evento_google="evento-7", eliminado_en=AHORA
    )
    calendario = CalendarioFalso()
    await sync_google.sincronizar_cita(sesion, cita.id, calendario)
    assert calendario.operaciones == [("eliminar", "evento-7")]


async def test_sync_sin_google_conectado_no_hace_nada(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    cita = await _cita(sesion, doctor, paciente, AHORA)
    calendario = CalendarioFalso()
    await sync_google.sincronizar_cita(sesion, cita.id, calendario)
    assert calendario.operaciones == [] and cita.estado_sync_google == EstadoSyncGoogle.PENDIENTE


async def test_sync_agotada_marca_error_y_alerta(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion, credenciales_google_calendar=_credenciales())
    paciente = await crear_paciente(sesion)
    cita = await _cita(sesion, doctor, paciente, AHORA)
    with pytest.raises(httpx.ConnectError):
        await sync_google.sincronizar_cita(sesion, cita.id, CalendarioFalso(falla=True))
    await sync_google.marcar_error(sesion, cita.id)  # lo que hace la tarea al agotar reintentos
    assert cita.estado_sync_google == EstadoSyncGoogle.ERROR
    alerta = (await sesion.execute(select(AlertaRecepcion))).scalar_one()
    assert alerta.id_doctor == doctor.id and "Google Calendar" in alerta.mensaje_ia


def test_tarea_celery_reintenta_con_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.worker import tareas_calendar

    async def falla(_: uuid.UUID) -> None:
        raise httpx.ConnectError("google caido")

    marcadas: list[uuid.UUID] = []

    async def marcar(id_cita: uuid.UUID) -> None:
        marcadas.append(id_cita)

    monkeypatch.setattr(tareas_calendar, "_sincronizar", falla)
    monkeypatch.setattr(tareas_calendar, "_marcar_error", marcar)
    id_cita = uuid.uuid4()
    tarea = tareas_calendar.sincronizar_cita_google
    resultado = tarea.apply(args=[str(id_cita)])  # ejecuta en linea, con reintentos
    assert resultado.successful()
    assert marcadas == [id_cita]  # GC-02: tras agotar reintentos


async def test_token_expirado_se_refresca_y_se_guarda_cifrado(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(sesion, credenciales_google_calendar=_credenciales(-10))
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        if peticion.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "acc-2", "expires_in": 3600})
        return httpx.Response(200, json={"id": "evento-9"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        id_evento = await ClienteGoogleCalendar(http).crear_evento(doctor, {"summary": "Consulta"})
    assert id_evento == "evento-9"
    assert parse_qs(peticiones[0].content.decode())["refresh_token"] == ["ref-1"]
    assert peticiones[1].headers["Authorization"] == "Bearer acc-2"
    guardadas = json.loads(doctor.credenciales_google_calendar)
    assert guardadas["access_token"] == "acc-2" and guardadas["refresh_token"] == "ref-1"


async def test_oauth_iniciar_y_callback(
    api: httpx.AsyncClient, sesion: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await crear_usuario(sesion)
    doctor = await crear_doctor(sesion)
    inicio = await api.get(
        "/google/oauth/iniciar", params={"id_doctor": str(doctor.id)}, headers=cabeceras(admin)
    )
    consulta = parse_qs(urlparse(inicio.json()["url"]).query)
    assert consulta["access_type"] == ["offline"] and consulta["scope"] == [oauth.SCOPE]
    estado = consulta["state"][0]

    async def intercambio(_: httpx.AsyncClient, codigo: str) -> dict[str, Any]:
        assert codigo == "codigo-123"
        return {"access_token": "a", "refresh_token": "r", "expira_en": 1}

    monkeypatch.setattr(oauth, "intercambiar_codigo", intercambio)
    malo = await api.get("/google/oauth/callback", params={"code": "codigo-123", "state": "x"})
    assert malo.status_code == 400
    ok = await api.get("/google/oauth/callback", params={"code": "codigo-123", "state": estado})
    assert ok.status_code == 200 and "Google Calendar conectado" in ok.text
    assert json.loads(doctor.credenciales_google_calendar)["refresh_token"] == "r"
    visto = await api.get(f"/doctores/{doctor.id}", headers=cabeceras(admin))
    assert visto.json()["google_calendar_conectado"] is True
    assert "credenciales" not in visto.text
