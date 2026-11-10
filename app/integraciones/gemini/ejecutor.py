"""Ejecucion de las tools de la IA contra la agenda (IA-06..IA-11, reglas IA-12)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modelos.doctor import Doctor
from app.modelos.enums import OrigenCita
from app.modelos.recordatorio import Recordatorio
from app.repositorios import auditoria
from app.servicios import agenda, alertas
from app.servicios import pacientes as servicio_pacientes

MENSAJE_DELEGACION = "El doctor dio una instruccion que debe ejecutar recepcion."


class ArgumentoInvalido(Exception):
    """Argumento de tool invalido. El mensaje va al modelo: sin datos de pacientes."""


class EjecutorTools:
    def __init__(self, sesion: AsyncSession, doctor: Doctor) -> None:
        self._sesion = sesion
        self._doctor = doctor
        self._tz = ZoneInfo(doctor.zona_horaria)
        self._actor = auditoria.actor_ia(doctor.id)
        self.citas_creadas: list[uuid.UUID] = []

    async def ejecutar(self, nombre: str, args: dict[str, Any]) -> dict[str, Any]:
        metodo = getattr(self, f"_tool_{nombre}", None)
        if metodo is None:
            return {"ok": False, "error": "herramienta desconocida"}
        try:
            return await metodo(**args)
        except ArgumentoInvalido as error:
            return {"ok": False, "error": str(error)}
        except TypeError:
            return {"ok": False, "error": "argumentos invalidos para la herramienta"}

    # ---------- utilidades ----------
    def _fecha_hora(self, iso: str) -> datetime:
        try:
            valor = datetime.fromisoformat(str(iso))
        except ValueError:
            raise ArgumentoInvalido("fecha_hora_iso no es ISO 8601 valido") from None
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=self._tz)
        if valor <= agenda.ahora_utc():
            raise ArgumentoInvalido("la fecha y hora ya pasaron; pide aclaracion al doctor")
        return valor

    def _duracion(self, minutos: Any) -> int:
        if minutos is None:
            return self._doctor.duracion_cita_default_min
        try:
            valor = int(minutos)
        except (TypeError, ValueError):
            raise ArgumentoInvalido("duracion_minutos debe ser un entero") from None
        if not 5 <= valor <= 480:
            raise ArgumentoInvalido("duracion_minutos debe estar entre 5 y 480")
        return valor

    def _local(self, valor: datetime) -> str:
        return valor.astimezone(self._tz).isoformat(timespec="minutes")

    # ---------- tools ----------
    async def _tool_buscar_paciente(self, nombre: str) -> dict[str, Any]:
        encontrados = await servicio_pacientes.buscar(self._sesion, str(nombre), limite=10)
        return {
            "ok": True,
            "total": len(encontrados),
            "coincidencias": [
                {"id_paciente": str(p.id), "nombre_completo": p.nombre_completo}
                for p in encontrados
            ],
        }

    async def _tool_consultar_disponibilidad(
        self, fecha: str, duracion_minutos: Any = None
    ) -> dict[str, Any]:
        try:
            dia = date.fromisoformat(str(fecha)[:10])
        except ValueError:
            raise ArgumentoInvalido("fecha debe tener formato AAAA-MM-DD") from None
        duracion = self._duracion(duracion_minutos)
        huecos = await agenda.huecos_libres(self._sesion, self._doctor, dia, duracion)
        return {
            "ok": True,
            "fecha": dia.isoformat(),
            "duracion_minutos": duracion,
            "horarios_libres": [h.strftime("%H:%M") for h in huecos],
        }

    async def _tool_agendar_cita(
        self,
        fecha_hora_iso: str,
        id_paciente: str | None = None,
        nombre_paciente_nuevo: str | None = None,
        duracion_minutos: Any = None,
        motivo: str | None = None,
    ) -> dict[str, Any]:
        if bool(id_paciente) == bool(nombre_paciente_nuevo):
            raise ArgumentoInvalido("indica id_paciente o nombre_paciente_nuevo, solo uno")
        inicio = self._fecha_hora(fecha_hora_iso)
        fin = inicio + timedelta(minutes=self._duracion(duracion_minutos))

        if nombre_paciente_nuevo:
            normalizado = servicio_pacientes.normalizar_nombre(nombre_paciente_nuevo)
            if not normalizado:
                raise ArgumentoInvalido("nombre_paciente_nuevo esta vacio")
            existentes = [
                p
                for p in await servicio_pacientes.buscar(self._sesion, nombre_paciente_nuevo)
                if p.nombre_normalizado == normalizado
            ]
            if existentes:
                return {
                    "ok": False,
                    "error": "ya existe un paciente con ese nombre; confirma con el doctor "
                    "si es el mismo (usa id_paciente) o delega a recepcion",
                    "coincidencias": [
                        {"id_paciente": str(p.id), "nombre_completo": p.nombre_completo}
                        for p in existentes
                    ],
                }
        try:
            # Savepoint: si el horario choca, tampoco queda creado el paciente nuevo.
            async with self._sesion.begin_nested():
                if nombre_paciente_nuevo:
                    paciente = await servicio_pacientes.crear(
                        self._sesion,
                        {"nombre_completo": " ".join(nombre_paciente_nuevo.split())},
                        self._actor,
                    )
                else:
                    try:
                        id_valido = uuid.UUID(str(id_paciente))
                    except ValueError:
                        raise ArgumentoInvalido(
                            "id_paciente invalido; usa buscar_paciente"
                        ) from None
                    existente = await servicio_pacientes.obtener(self._sesion, id_valido)
                    if existente is None:
                        raise ArgumentoInvalido("id_paciente no existe; usa buscar_paciente")
                    paciente = existente
                cita = await agenda.crear_cita(
                    self._sesion,
                    doctor=self._doctor,
                    id_paciente=paciente.id,
                    inicio=inicio,
                    fin=fin,
                    motivo=motivo,
                    origen=OrigenCita.IA,
                    actor=self._actor,
                )
        except agenda.HorarioOcupado as error:
            return {
                "ok": False,
                "error": "horario ocupado",
                "alternativas": [self._local(a) for a in error.alternativas],
            }
        self.citas_creadas.append(cita.id)
        return {
            "ok": True,
            "paciente": paciente.nombre_completo,
            "paciente_nuevo": bool(nombre_paciente_nuevo),
            "inicio": self._local(cita.fecha_hora_inicio),
            "fin": self._local(cita.fecha_hora_fin),
        }

    async def _tool_crear_recordatorio_tarea(
        self, fecha_hora_iso: str, descripcion_tarea: str
    ) -> dict[str, Any]:
        if not str(descripcion_tarea).strip():
            raise ArgumentoInvalido("descripcion_tarea esta vacia")
        cuando = self._fecha_hora(fecha_hora_iso)
        recordatorio = Recordatorio(
            id_doctor=self._doctor.id, fecha_hora=cuando, descripcion=str(descripcion_tarea)
        )
        self._sesion.add(recordatorio)
        await self._sesion.flush()
        await auditoria.registrar(
            self._sesion,
            entidad="recordatorio",
            id_entidad=recordatorio.id,
            accion="crear",
            actor=self._actor,
            cambios={"fecha_hora": cuando},
        )
        return {"ok": True, "fecha_hora": self._local(cuando)}

    async def _tool_delegar_a_recepcion(self, instruccion_literal: str) -> dict[str, Any]:
        if not str(instruccion_literal).strip():
            raise ArgumentoInvalido("instruccion_literal esta vacia")
        await alertas.crear(
            self._sesion,
            id_doctor=self._doctor.id,
            mensaje_ia=MENSAJE_DELEGACION,
            instruccion_original=str(instruccion_literal),
            actor=self._actor,
        )
        return {"ok": True, "resultado": "alerta creada para recepcion"}
