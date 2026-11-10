"""Fase 3 y 4: webhook (WA-*), IA con tools (IA-04..14) y pipeline de audio (IA-01..03)."""

import hashlib
import hmac
import json
import struct
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_webhooks import main as webhooks
from app.core.config import obtener_config
from app.integraciones.gemini.cliente import LlamadaTool, RespuestaIA
from app.integraciones.gemini.orquestador import (
    RESPUESTA_LIMITE,
    EntradaDoctor,
    cargar_historial,
    clave_cierre_pendiente,
    procesar_instruccion,
)
from app.integraciones.gemini.prompt import construir_system_prompt
from app.integraciones.gemini.tools import DECLARACIONES
from app.integraciones.whatsapp.cliente import (
    ClienteWhatsApp,
    Media,
    MediaDemasiadoGrande,
    candidatos_e164,
)
from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.cita import Cita
from app.modelos.enums import OrigenCita
from app.modelos.paciente import Paciente
from app.modelos.recordatorio import Recordatorio
from app.servicios import mensajes
from app.worker import despacho
from tests.conftest import RedisFalso, crear_doctor, crear_paciente

TZ = ZoneInfo("America/Mexico_City")
MANANA_17 = (datetime.now(TZ) + timedelta(days=1)).replace(
    hour=17, minute=0, second=0, microsecond=0
)


# ---------- dobles de prueba ----------
class IAFalsa:
    """Devuelve respuestas guionizadas y guarda lo que recibio."""

    def __init__(self, *respuestas: RespuestaIA) -> None:
        self._respuestas = list(respuestas)
        self.llamadas: list[dict[str, Any]] = []

    async def generar(self, *, sistema: str, contenidos: list[Any]) -> RespuestaIA:
        self.llamadas.append({"sistema": sistema, "contenidos": list(contenidos)})
        return self._respuestas.pop(0)

    def resultado_tool(self, turno: int) -> dict[str, Any]:
        """Respuesta de tool que el modelo recibio antes de su llamada numero `turno`."""
        return self.llamadas[turno]["contenidos"][-1].parts[0].function_response.response


def tool(nombre_tool: str, /, **args: Any) -> RespuestaIA:
    return RespuestaIA(llamadas=[LlamadaTool(nombre_tool, args)])


def texto(valor: str) -> RespuestaIA:
    return RespuestaIA(texto=valor)


class WAFalso:
    def __init__(self, media: Media | Exception | None = None) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.plantillas: list[tuple[str, str, list[str]]] = []
        self._media = media

    async def enviar_texto(self, telefono: str, texto: str) -> None:
        self.enviados.append((telefono, texto))

    async def enviar_plantilla(self, telefono: str, nombre: str, parametros: list[str]) -> None:
        self.plantillas.append((telefono, nombre, parametros))

    async def descargar_media(self, media_id: str, max_bytes: int) -> Media:
        if isinstance(self._media, Exception):
            raise self._media
        assert self._media is not None
        return self._media


def ogg_falso(segundos: float) -> bytes:
    """Pagina OGG minima cuya posicion granular equivale a `segundos` (48 kHz)."""
    return b"OggS\x00\x04" + struct.pack("<q", int(segundos * 48000)) + b"\x00" * 16


# ---------- webhook ----------
@pytest.fixture
async def wh(
    redis: RedisFalso, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    encolados: list[dict[str, Any]] = []
    monkeypatch.setattr(despacho, "encolar_mensaje_whatsapp", encolados.append)
    webhooks.app.dependency_overrides[webhooks.obtener_redis] = lambda: redis
    transporte = httpx.ASGITransport(app=webhooks.app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://test") as cliente:
        cliente.encolados = encolados  # type: ignore[attr-defined]
        yield cliente
    webhooks.app.dependency_overrides.clear()


def _firmado(carga: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    cuerpo = json.dumps(carga).encode()
    firma = hmac.new(obtener_config().wa_app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return cuerpo, {"X-Hub-Signature-256": f"sha256={firma}", "Content-Type": "application/json"}


def _carga(*mensajes_wa: dict[str, Any]) -> dict[str, Any]:
    return {"entry": [{"changes": [{"value": {"messages": list(mensajes_wa)}}]}]}


async def test_webhook_verificacion(wh: httpx.AsyncClient) -> None:
    parametros = {"hub.mode": "subscribe", "hub.challenge": "12345"}
    ok = await wh.get(
        "/webhooks/whatsapp", params={**parametros, "hub.verify_token": "verify-de-pruebas"}
    )
    assert ok.status_code == 200 and ok.text == "12345"
    mal = await wh.get("/webhooks/whatsapp", params={**parametros, "hub.verify_token": "otro"})
    assert mal.status_code == 403


async def test_webhook_firma_invalida(wh: httpx.AsyncClient) -> None:
    cuerpo, cabeceras = _firmado(_carga({"id": "wamid.1", "from": "5215511112222", "type": "text"}))
    sin_firma = await wh.post("/webhooks/whatsapp", content=cuerpo)
    alterado = await wh.post("/webhooks/whatsapp", content=cuerpo + b" ", headers=cabeceras)
    assert sin_firma.status_code == 401 and alterado.status_code == 401
    assert wh.encolados == []  # type: ignore[attr-defined]


async def test_webhook_encola_y_deduplica(wh: httpx.AsyncClient, redis: RedisFalso) -> None:
    mensaje = {"id": "wamid.A", "from": "5215511112222", "type": "text", "text": {"body": "hola"}}
    cuerpo, cabeceras = _firmado(_carga(mensaje))
    primera = await wh.post("/webhooks/whatsapp", content=cuerpo, headers=cabeceras)
    reintento = await wh.post("/webhooks/whatsapp", content=cuerpo, headers=cabeceras)
    assert primera.status_code == 200 and reintento.status_code == 200
    assert wh.encolados == [mensaje]  # type: ignore[attr-defined]
    assert redis.ttl["wa_msg:wamid.A"] == 48 * 3600
    # Notificaciones de estado (sin messages) se responden 200 sin encolar.
    cuerpo, cabeceras = _firmado({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]})
    assert (
        await wh.post("/webhooks/whatsapp", content=cuerpo, headers=cabeceras)
    ).status_code == 200
    assert len(wh.encolados) == 1  # type: ignore[attr-defined]


async def test_webhook_libera_marca_si_no_puede_encolar(
    wh: httpx.AsyncClient, redis: RedisFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falla(_: dict[str, Any]) -> None:
        raise ConnectionError("broker caido")

    monkeypatch.setattr(despacho, "encolar_mensaje_whatsapp", falla)
    cuerpo, cabeceras = _firmado(_carga({"id": "wamid.B", "from": "1", "type": "text"}))
    respuesta = await wh.post("/webhooks/whatsapp", content=cuerpo, headers=cabeceras)
    assert respuesta.status_code == 503  # Meta reintentara
    assert "wa_msg:wamid.B" not in redis.datos


# ---------- prompt y declaraciones ----------
async def test_system_prompt_usa_zona_del_doctor(sesion: AsyncSession) -> None:
    doctor = await crear_doctor(
        sesion, zona_horaria="America/Tijuana", duracion_cita_default_min=45
    )
    ahora = datetime(2026, 11, 11, 3, 30, tzinfo=UTC)  # 10 nov 19:30 en Tijuana
    prompt = construir_system_prompt(doctor, ahora)
    assert "martes 2026-11-10T19:30-08:00" in prompt
    assert "45 minutos" in prompt
    assert "Nunca inventes pacientes" in prompt
    con_cierre = construir_system_prompt(doctor, ahora, "¿Hay pendientes?")
    assert "¿Hay pendientes?" in con_cierre


def test_tools_declaradas_segun_spec() -> None:
    nombres = [d["name"] for d in DECLARACIONES]
    assert nombres == [
        "buscar_paciente",
        "consultar_disponibilidad",
        "agendar_cita",
        "crear_recordatorio_tarea",
        "delegar_a_recepcion",
        "solicitar_aclaracion",
    ]
    agendar = DECLARACIONES[2]["parameters_json_schema"]["properties"]
    assert set(agendar) == {
        "id_paciente",
        "nombre_paciente_nuevo",
        "fecha_hora_iso",
        "duracion_minutos",
        "motivo",
    }


# ---------- orquestador ----------
async def _procesar(sesion, redis, doctor, ia, instruccion="Agenda a Ana mañana a las 5"):
    return await procesar_instruccion(
        sesion=sesion, redis=redis, doctor=doctor, entrada=EntradaDoctor(texto=instruccion), ia=ia
    )


async def test_ia_agenda_con_coincidencia_unica(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion, "Ana López")
    ia = IAFalsa(
        tool("buscar_paciente", nombre="Ana"),
        tool(
            "agendar_cita",
            id_paciente=str(paciente.id),
            fecha_hora_iso=MANANA_17.isoformat(),
            motivo="control",
        ),
        texto("Agendé a Ana López mañana 17:00–17:30"),
    )
    resultado = await _procesar(sesion, redis, doctor, ia)
    assert resultado.respuesta == "Agendé a Ana López mañana 17:00–17:30"
    assert ia.resultado_tool(1)["total"] == 1
    confirmacion = ia.resultado_tool(2)
    assert confirmacion["ok"] and confirmacion["inicio"] == MANANA_17.isoformat(timespec="minutes")
    cita = (await sesion.execute(select(Cita))).scalar_one()
    assert cita.origen == OrigenCita.IA and cita.motivo_consulta == "control"
    assert cita.fecha_hora_inicio == MANANA_17
    assert cita.fecha_hora_fin - cita.fecha_hora_inicio == timedelta(minutes=30)
    assert resultado.citas_creadas == [cita.id]
    # IA-04: historial con TTL.
    historial = await cargar_historial(redis, doctor.id)
    assert [t["rol"] for t in historial] == ["user", "model"]
    assert redis.ttl[f"chat:{doctor.id}"] == 7200


async def test_ia_horario_ocupado_devuelve_alternativas_y_no_crea_paciente(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    existente = await crear_paciente(sesion, "Ana López")
    sesion.add(
        Cita(
            id_doctor=doctor.id,
            id_paciente=existente.id,
            fecha_hora_inicio=MANANA_17,
            fecha_hora_fin=MANANA_17 + timedelta(minutes=30),
            origen=OrigenCita.RECEPCION,
        )
    )
    await sesion.flush()
    ia = IAFalsa(
        tool(
            "agendar_cita",
            nombre_paciente_nuevo="Carlos Peña",
            fecha_hora_iso=MANANA_17.isoformat(),
        ),
        texto("Ese horario está ocupado. Tengo 16:30 o 17:30."),
    )
    await _procesar(sesion, redis, doctor, ia, "Agenda a Carlos Peña, paciente nuevo, mañana 5pm")
    choque = ia.resultado_tool(1)
    assert choque["ok"] is False and choque["error"] == "horario ocupado"
    assert (
        MANANA_17.replace(hour=16, minute=30).isoformat(timespec="minutes")
        in choque["alternativas"]
    )
    total_pacientes = (
        await sesion.execute(select(func.count()).select_from(Paciente))
    ).scalar_one()
    assert total_pacientes == 1  # el paciente nuevo no quedo creado
    assert (await sesion.execute(select(func.count()).select_from(Cita))).scalar_one() == 1


async def test_ia_paciente_nuevo_y_proteccion_contra_duplicados(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    await crear_paciente(sesion, "Ana López")
    ia = IAFalsa(
        tool(
            "agendar_cita", nombre_paciente_nuevo="ana lopez", fecha_hora_iso=MANANA_17.isoformat()
        ),
        tool(
            "agendar_cita",
            nombre_paciente_nuevo="Carlos  Peña",
            fecha_hora_iso=MANANA_17.isoformat(),
        ),
        texto("Agendé a Carlos Peña mañana 17:00–17:30"),
    )
    await _procesar(sesion, redis, doctor, ia)
    assert ia.resultado_tool(1)["ok"] is False  # ya existe "Ana López": no se duplica
    assert ia.resultado_tool(2)["paciente_nuevo"] is True
    nombres = (await sesion.execute(select(Paciente.nombre_completo))).scalars().all()
    assert sorted(nombres) == ["Ana López", "Carlos Peña"]


async def test_ia_varias_coincidencias_delega_a_recepcion(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    await crear_paciente(sesion, "Ana López")
    await crear_paciente(sesion, "Ana María Torres")
    literal = "Cancela la cita de Ana del jueves y avísale"
    ia = IAFalsa(
        tool("buscar_paciente", nombre="Ana"),
        tool("delegar_a_recepcion", instruccion_literal=literal),
        texto("Pasé tu instrucción a recepción."),
    )
    resultado = await _procesar(sesion, redis, doctor, ia, literal)
    assert ia.resultado_tool(1)["total"] == 2
    alerta = (await sesion.execute(select(AlertaRecepcion))).scalar_one()
    assert alerta.instruccion_original == literal and alerta.id_doctor == doctor.id
    assert resultado.citas_creadas == []


async def test_ia_solicitar_aclaracion_termina_el_turno(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    doctor = await crear_doctor(sesion)
    ia = IAFalsa(tool("solicitar_aclaracion", pregunta="¿A qué hora mañana?"))
    resultado = await _procesar(sesion, redis, doctor, ia, "Agenda a Ana mañana")
    assert resultado.respuesta == "¿A qué hora mañana?"
    assert len(ia.llamadas) == 1
    # El siguiente mensaje lleva el historial previo como contexto.
    ia2 = IAFalsa(texto("Listo"))
    await _procesar(sesion, redis, doctor, ia2, "A las 5")
    previos = [c.parts[0].text for c in ia2.llamadas[0]["contenidos"]]
    assert previos == ["Agenda a Ana mañana", "¿A qué hora mañana?", "A las 5"]


async def test_ia_limite_de_iteraciones_delega(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    ia = IAFalsa(*[tool("buscar_paciente", nombre="Ana") for _ in range(10)])
    resultado = await _procesar(sesion, redis, doctor, ia)
    assert len(ia.llamadas) == 5  # IA-14
    assert resultado.respuesta == RESPUESTA_LIMITE
    assert (await sesion.execute(select(AlertaRecepcion))).scalar_one()


async def test_ia_argumentos_invalidos_no_rompen(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    ayer = (datetime.now(TZ) - timedelta(days=1)).isoformat()
    ia = IAFalsa(
        tool("agendar_cita", id_paciente=str(uuid.uuid4()), fecha_hora_iso=ayer),
        tool("agendar_cita", id_paciente="no-uuid", fecha_hora_iso=MANANA_17.isoformat()),
        tool("herramienta_inexistente"),
        tool("consultar_disponibilidad", fecha="mañana"),
        texto("No pude agendar."),
    )
    await _procesar(sesion, redis, doctor, ia)
    assert [ia.resultado_tool(i)["ok"] for i in range(1, 5)] == [False] * 4
    assert (await sesion.execute(select(func.count()).select_from(Cita))).scalar_one() == 0


async def test_ia_recordatorio_y_disponibilidad(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    sesion.add(
        Cita(
            id_doctor=doctor.id,
            id_paciente=paciente.id,
            fecha_hora_inicio=MANANA_17,
            fecha_hora_fin=MANANA_17 + timedelta(minutes=30),
            origen=OrigenCita.RECEPCION,
        )
    )
    await sesion.flush()
    ia = IAFalsa(
        tool("consultar_disponibilidad", fecha=MANANA_17.date().isoformat()),
        tool(
            "crear_recordatorio_tarea",
            fecha_hora_iso=MANANA_17.isoformat(),
            descripcion_tarea="Revisar estudios de Ana",
        ),
        texto("Te recuerdo mañana a las 17:00."),
    )
    await _procesar(sesion, redis, doctor, ia)
    libres = ia.resultado_tool(1)["horarios_libres"]
    assert "17:00" not in libres and "16:30" in libres and "17:30" in libres
    assert libres[0] == "08:00" and libres[-1] == "19:30"
    recordatorio = (await sesion.execute(select(Recordatorio))).scalar_one()
    assert recordatorio.descripcion == "Revisar estudios de Ana"
    assert recordatorio.fecha_hora == MANANA_17


async def test_ia_contexto_de_cierre_se_consume(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    await redis.set(clave_cierre_pendiente(doctor.id), "¿Hay pendientes?")
    ia = IAFalsa(texto("Anotado."))
    await _procesar(sesion, redis, doctor, ia, "Sí, llamar al laboratorio")
    assert "¿Hay pendientes?" in ia.llamadas[0]["sistema"]
    assert await redis.get(clave_cierre_pendiente(doctor.id)) is None  # IA-17


# ---------- manejo de mensajes ----------
def _mensaje(doctor, tipo="text", **extra) -> dict[str, Any]:
    base = {"id": "wamid.X", "from": doctor.telefono_whatsapp.lstrip("+"), "type": tipo}
    return {**base, **extra}


async def test_mensaje_de_numero_no_registrado_se_ignora(
    sesion: AsyncSession, redis: RedisFalso
) -> None:
    wa, ia = WAFalso(), IAFalsa()
    resultado = await mensajes.manejar_mensaje(
        sesion=sesion,
        redis=redis,
        wa=wa,
        ia=ia,
        mensaje={"id": "1", "from": "5215599990000", "type": "text", "text": {"body": "hola"}},
    )
    assert resultado is None and wa.enviados == [] and ia.llamadas == []  # WA-04


async def test_mensaje_texto_responde_al_doctor(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion, telefono_whatsapp="+525511223344")
    wa, ia = WAFalso(), IAFalsa(texto("Hecho"))
    # Mexico: WhatsApp entrega 521... aunque el numero registrado sea +52...
    mensaje = {"id": "1", "from": "5215511223344", "type": "text", "text": {"body": "hola"}}
    resultado = await mensajes.manejar_mensaje(
        sesion=sesion, redis=redis, wa=wa, ia=ia, mensaje=mensaje
    )
    assert resultado is not None
    assert wa.enviados == [("5215511223344", "Hecho")]
    assert redis.ttl[mensajes.clave_ventana(doctor.id)] == 24 * 3600


async def test_mensaje_tipo_no_soportado(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    wa, ia = WAFalso(), IAFalsa()
    await mensajes.manejar_mensaje(
        sesion=sesion, redis=redis, wa=wa, ia=ia, mensaje=_mensaje(doctor, "image")
    )
    assert wa.enviados[0][1] == mensajes.MSJ_TIPO_NO_SOPORTADO and ia.llamadas == []  # WA-05


async def test_audio_va_inline_a_la_ia(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    audio = ogg_falso(45)
    wa, ia = WAFalso(Media(datos=audio, mime_type="audio/ogg")), IAFalsa(texto("Entendido"))
    await mensajes.manejar_mensaje(
        sesion=sesion,
        redis=redis,
        wa=wa,
        ia=ia,
        mensaje=_mensaje(doctor, "audio", audio={"id": "media-1"}),
    )
    parte = ia.llamadas[0]["contenidos"][-1].parts[0]
    assert parte.inline_data.data == audio and parte.inline_data.mime_type == "audio/ogg"
    assert wa.enviados[-1][1] == "Entendido"
    # IA-02: en el historial no queda el audio, solo una marca.
    assert (await cargar_historial(redis, doctor.id))[0]["texto"] == "[nota de voz]"


@pytest.mark.parametrize(
    "media", [Media(datos=ogg_falso(200), mime_type="audio/ogg"), MediaDemasiadoGrande()]
)
async def test_audio_largo_pide_dividir(
    sesion: AsyncSession, redis: RedisFalso, media: Media | Exception
) -> None:
    doctor = await crear_doctor(sesion)
    wa, ia = WAFalso(media), IAFalsa()
    await mensajes.manejar_mensaje(
        sesion=sesion,
        redis=redis,
        wa=wa,
        ia=ia,
        mensaje=_mensaje(doctor, "audio", audio={"id": "media-1"}),
    )
    assert "menos de 2 minutos" in wa.enviados[0][1] and ia.llamadas == []  # IA-03


async def test_limite_de_mensajes_por_doctor(sesion: AsyncSession, redis: RedisFalso) -> None:
    doctor = await crear_doctor(sesion)
    limite = obtener_config().limite_mensajes_por_minuto
    wa, ia = WAFalso(), IAFalsa(*[texto("ok")] * limite)
    for _ in range(limite + 1):
        await mensajes.manejar_mensaje(
            sesion=sesion,
            redis=redis,
            wa=wa,
            ia=ia,
            mensaje=_mensaje(doctor, text={"body": "hola"}),
        )
    assert len(ia.llamadas) == limite  # SEG-04
    assert wa.enviados[-1][1] == mensajes.MSJ_LIMITE


async def test_fallo_de_ia_no_filtra_phi_y_avisa(
    sesion: AsyncSession, redis: RedisFalso, caplog: pytest.LogCaptureFixture
) -> None:
    doctor = await crear_doctor(sesion)

    class IARota:
        async def generar(self, **_: Any) -> RespuestaIA:
            raise RuntimeError("fallo con datos de la paciente Ana López")

    wa = WAFalso()
    await mensajes.manejar_mensaje(
        sesion=sesion,
        redis=redis,
        wa=wa,
        ia=IARota(),
        mensaje=_mensaje(doctor, text={"body": "Agenda a Ana López"}),
    )
    assert wa.enviados[0][1] == mensajes.MSJ_ERROR
    assert "Ana" not in caplog.text and "RuntimeError" in caplog.text


# ---------- cliente de WhatsApp (HTTP simulado) ----------
def test_candidatos_e164_mexico() -> None:
    assert candidatos_e164("5215511223344") == ["+5215511223344", "+525511223344"]
    assert candidatos_e164("14155550100") == ["+14155550100"]


async def test_cliente_whatsapp_descarga_en_dos_pasos() -> None:
    vistos: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        vistos.append(peticion)
        if peticion.url.host == "graph.facebook.com" and peticion.method == "GET":
            return httpx.Response(
                200,
                json={
                    "url": "https://cdn.test/a.ogg",
                    "mime_type": "audio/ogg; codecs=opus",
                    "file_size": 3,
                },
            )
        if peticion.url.host == "cdn.test":
            return httpx.Response(200, content=b"abc")
        return httpx.Response(200, json={"messages": [{"id": "x"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        cliente = ClienteWhatsApp(http)
        media = await cliente.descargar_media("media-9", max_bytes=10)
        assert media == Media(datos=b"abc", mime_type="audio/ogg")
        with pytest.raises(MediaDemasiadoGrande):
            await cliente.descargar_media("media-9", max_bytes=2)
        await cliente.enviar_texto("+525511223344", "hola")
        await cliente.enviar_plantilla("+525511223344", "cierre_diario", ["Dra. Ruiz", "3"])
    assert all(p.headers["Authorization"] == "Bearer token-de-pruebas" for p in vistos)
    envio_texto, envio_plantilla = (json.loads(p.content) for p in vistos[-2:])
    assert envio_texto["to"] == "525511223344" and envio_texto["text"]["body"] == "hola"
    assert envio_plantilla["template"]["name"] == "cierre_diario"
    assert envio_plantilla["template"]["language"]["code"] == "es_MX"
    parametros = envio_plantilla["template"]["components"][0]["parameters"]
    assert [p["text"] for p in parametros] == ["Dra. Ruiz", "3"]
