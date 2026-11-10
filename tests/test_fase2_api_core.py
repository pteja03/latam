"""Fase 2: auth (SEG-03) y CRUD de doctores, pacientes, citas y alertas."""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.enums import EstadoAlerta, RolUsuario
from app.modelos.log_auditoria import LogAuditoria
from app.servicios import alertas as servicio_alertas
from tests.conftest import cabeceras, crear_doctor, crear_paciente, crear_usuario

MANANA_17 = (datetime.now(UTC) + timedelta(days=1)).replace(
    hour=17, minute=0, second=0, microsecond=0
)


async def test_login_y_yo(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    usuario = await crear_usuario(sesion, password="clave-correcta")
    mal = await api.post("/auth/login", json={"correo": usuario.correo, "password": "otra"})
    assert mal.status_code == 401
    bien = await api.post(
        "/auth/login", json={"correo": usuario.correo.upper(), "password": "clave-correcta"}
    )
    assert bien.status_code == 200
    token = bien.json()["access_token"]
    yo = await api.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert yo.json()["correo"] == usuario.correo
    assert "hash_password" not in yo.json()


async def test_endpoints_requieren_token(api: httpx.AsyncClient) -> None:
    for ruta in ("/doctores", "/citas", "/alertas", "/dashboard/kpis", "/pacientes?q=ana"):
        assert (await api.get(ruta)).status_code == 401
    assert (await api.get("/doctores", headers={"Authorization": "Bearer x"})).status_code == 401


async def test_crud_doctor_solo_admin(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    admin = await crear_usuario(sesion)
    recepcion = await crear_usuario(sesion, RolUsuario.RECEPCION)
    datos = {"nombre": "Dr. Luis Vega", "telefono_whatsapp": "+525511112222"}
    assert (
        await api.post("/doctores", json=datos, headers=cabeceras(recepcion))
    ).status_code == 403
    creado = await api.post("/doctores", json=datos, headers=cabeceras(admin))
    assert creado.status_code == 201
    assert creado.json()["duracion_cita_default_min"] == 30
    assert creado.json()["google_calendar_conectado"] is False
    duplicado = await api.post("/doctores", json=datos, headers=cabeceras(admin))
    assert duplicado.status_code == 409
    mala_zona = await api.post(
        "/doctores", json={**datos, "zona_horaria": "Marte/Olimpo"}, headers=cabeceras(admin)
    )
    assert mala_zona.status_code == 422

    id_doctor = creado.json()["id"]
    borrado = await api.delete(f"/doctores/{id_doctor}", headers=cabeceras(admin))
    assert borrado.status_code == 204
    # Soft delete: la fila sigue existiendo con eliminado_en.
    fila = (
        await sesion.execute(
            text("SELECT eliminado_en FROM doctor WHERE id = :i"), {"i": id_doctor}
        )
    ).scalar_one()
    assert fila is not None
    assert (await api.get(f"/doctores/{id_doctor}", headers=cabeceras(admin))).status_code == 404


async def test_pacientes_busqueda_sin_acentos(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    usuario = await crear_usuario(sesion)
    creado = await api.post(
        "/pacientes",
        json={"nombre_completo": "José Ángel Núñez", "notas_clinicas_breves": "hipertensión"},
        headers=cabeceras(usuario),
    )
    assert creado.status_code == 201
    encontrados = await api.get(
        "/pacientes", params={"q": "nunez jose"}, headers=cabeceras(usuario)
    )
    assert [p["nombre_completo"] for p in encontrados.json()] == ["José Ángel Núñez"]
    assert "notas_clinicas_breves" not in encontrados.json()[0]  # el listado no trae notas
    detalle = await api.get(f"/pacientes/{creado.json()['id']}", headers=cabeceras(usuario))
    assert detalle.json()["notas_clinicas_breves"] == "hipertensión"
    logs = await sesion.execute(select(LogAuditoria).where(LogAuditoria.entidad == "paciente"))
    assert all("hipertensión" not in str(log.cambios) for log in logs.scalars())


async def test_cita_crear_y_horario_ocupado(
    api: httpx.AsyncClient, sesion: AsyncSession, sync_encoladas: list
) -> None:
    usuario = await crear_usuario(sesion)
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    cuerpo = {
        "id_doctor": str(doctor.id),
        "id_paciente": str(paciente.id),
        "fecha_hora_inicio": MANANA_17.isoformat(),
        "motivo_consulta": "control",
    }
    creada = await api.post("/citas", json=cuerpo, headers=cabeceras(usuario))
    assert creada.status_code == 201, creada.text
    datos = creada.json()
    assert datos["paciente"]["nombre_completo"] == "Ana López"
    assert datos["origen"] == "recepcion" and datos["estado"] == "programada"
    fin = datetime.fromisoformat(datos["fecha_hora_fin"])
    assert fin - MANANA_17 == timedelta(minutes=30)  # duracion default del doctor
    assert [str(i) for i in sync_encoladas] == [datos["id"]]

    choque = await api.post(
        "/citas",
        json={**cuerpo, "fecha_hora_inicio": (MANANA_17 + timedelta(minutes=10)).isoformat()},
        headers=cabeceras(usuario),
    )
    assert choque.status_code == 409
    assert choque.json()["detail"] == "horario ocupado"
    alternativas = [datetime.fromisoformat(a) for a in choque.json()["alternativas"]]
    assert alternativas and all(a != MANANA_17 for a in alternativas)

    sin_zona = await api.post(
        "/citas",
        json={**cuerpo, "fecha_hora_inicio": "2030-01-01T10:00:00"},
        headers=cabeceras(usuario),
    )
    assert sin_zona.status_code == 422  # se exige offset


async def test_cita_reprogramar_cancelar_y_eliminar(
    api: httpx.AsyncClient, sesion: AsyncSession
) -> None:
    usuario = await crear_usuario(sesion)
    doctor = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    base = {"id_doctor": str(doctor.id), "id_paciente": str(paciente.id)}
    c1 = (
        await api.post(
            "/citas",
            json={**base, "fecha_hora_inicio": MANANA_17.isoformat()},
            headers=cabeceras(usuario),
        )
    ).json()
    c2 = (
        await api.post(
            "/citas",
            json={**base, "fecha_hora_inicio": (MANANA_17 + timedelta(hours=1)).isoformat()},
            headers=cabeceras(usuario),
        )
    ).json()
    # Reprogramar c2 encima de c1 -> 409 y c2 queda intacta.
    choque = await api.patch(
        f"/citas/{c2['id']}",
        json={"fecha_hora_inicio": MANANA_17.isoformat()},
        headers=cabeceras(usuario),
    )
    assert choque.status_code == 409
    intacta = (await api.get(f"/citas/{c2['id']}", headers=cabeceras(usuario))).json()
    assert intacta["fecha_hora_inicio"] == c2["fecha_hora_inicio"]
    # Cancelar c1 libera el horario.
    cancelada = await api.patch(
        f"/citas/{c1['id']}", json={"estado": "cancelada"}, headers=cabeceras(usuario)
    )
    assert cancelada.json()["estado"] == "cancelada"
    movida = await api.patch(
        f"/citas/{c2['id']}",
        json={"fecha_hora_inicio": MANANA_17.isoformat()},
        headers=cabeceras(usuario),
    )
    assert movida.status_code == 200
    fin = datetime.fromisoformat(movida.json()["fecha_hora_fin"])
    assert fin - MANANA_17 == timedelta(minutes=30)  # conserva la duracion
    # Eliminar = soft delete + auditoria.
    assert (await api.delete(f"/citas/{c2['id']}", headers=cabeceras(usuario))).status_code == 204
    assert (await api.get(f"/citas/{c2['id']}", headers=cabeceras(usuario))).status_code == 404
    filas = (await sesion.execute(text("SELECT count(*) FROM cita"))).scalar_one()
    assert filas == 2
    acciones = (
        (
            await sesion.execute(
                select(LogAuditoria.accion).where(LogAuditoria.id_entidad == c2["id"])
            )
        )
        .scalars()
        .all()
    )
    assert set(acciones) == {"crear", "actualizar", "eliminar"}


async def test_recepcion_solo_ve_sus_doctores(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    propio = await crear_doctor(sesion)
    ajeno = await crear_doctor(sesion)
    paciente = await crear_paciente(sesion)
    usuario = await crear_usuario(sesion, RolUsuario.RECEPCION, doctores=[propio.id])
    vistos = await api.get("/doctores", headers=cabeceras(usuario))
    assert [d["id"] for d in vistos.json()] == [str(propio.id)]
    prohibida = await api.post(
        "/citas",
        json={
            "id_doctor": str(ajeno.id),
            "id_paciente": str(paciente.id),
            "fecha_hora_inicio": MANANA_17.isoformat(),
        },
        headers=cabeceras(usuario),
    )
    assert prohibida.status_code == 403
    assert (
        await api.get("/citas", params={"id_doctor": str(ajeno.id)}, headers=cabeceras(usuario))
    ).status_code == 403


async def test_alertas_tomar_y_resolver(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    usuario = await crear_usuario(sesion)
    doctor = await crear_doctor(sesion)
    alerta = await servicio_alertas.crear(
        sesion,
        id_doctor=doctor.id,
        mensaje_ia="Requiere a recepcion",
        instruccion_original="Cancela la cita de Ana del jueves",
        actor="sistema",
    )
    lista = await api.get("/alertas", params={"estado": "pendiente"}, headers=cabeceras(usuario))
    assert lista.json()[0]["instruccion_original"] == "Cancela la cita de Ana del jueves"
    assert lista.json()[0]["nombre_doctor"] == doctor.nombre
    tomada = await api.post(f"/alertas/{alerta.id}/tomar", headers=cabeceras(usuario))
    assert tomada.json()["estado"] == EstadoAlerta.EN_PROCESO
    assert (
        await api.post(f"/alertas/{alerta.id}/tomar", headers=cabeceras(usuario))
    ).status_code == 409
    resuelta = await api.post(f"/alertas/{alerta.id}/resolver", headers=cabeceras(usuario))
    assert resuelta.json()["estado"] == EstadoAlerta.RESUELTA
    assert resuelta.json()["resuelta_por"] == str(usuario.id)
    assert resuelta.json()["resuelta_en"] is not None


async def test_kpis_del_dashboard(api: httpx.AsyncClient, sesion: AsyncSession) -> None:
    usuario = await crear_usuario(sesion)
    doctor = await crear_doctor(sesion, zona_horaria="UTC")
    paciente = await crear_paciente(sesion)
    medio_dia = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    ids = []
    for i in range(3):
        respuesta = await api.post(
            "/citas",
            json={
                "id_doctor": str(doctor.id),
                "id_paciente": str(paciente.id),
                "fecha_hora_inicio": (medio_dia + timedelta(minutes=30 * i)).isoformat(),
            },
            headers=cabeceras(usuario),
        )
        ids.append(respuesta.json()["id"])
    for id_cita, estado in zip(ids, ("en_espera", "atendida", "cancelada"), strict=True):
        await api.patch(f"/citas/{id_cita}", json={"estado": estado}, headers=cabeceras(usuario))
    kpis = await api.get(
        "/dashboard/kpis", params={"id_doctor": str(doctor.id)}, headers=cabeceras(usuario)
    )
    assert kpis.json() == {
        "citas_de_hoy": 2,
        "en_espera": 1,
        "atendidos": 1,
        "alertas_pendientes": 0,
    }
