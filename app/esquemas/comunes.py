"""Esquemas Pydantic de api_core."""

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modelos.enums import (
    EstadoAlerta,
    EstadoCita,
    EstadoSeguimiento,
    EstadoSyncGoogle,
    OrigenCita,
    RolUsuario,
)


class _Salida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _validar_zona(valor: str | None) -> str | None:
    if valor is None:
        return valor
    try:
        ZoneInfo(valor)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("zona_horaria debe ser una zona IANA valida") from None
    return valor


# ---------- Auth / usuarios ----------
class LoginEntrada(BaseModel):
    correo: str
    password: str


class TokenSalida(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    correo: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    rol: RolUsuario = RolUsuario.RECEPCION
    doctores_asignados: list[uuid.UUID] = []


class UsuarioActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    rol: RolUsuario | None = None
    doctores_asignados: list[uuid.UUID] | None = None


class UsuarioSalida(_Salida):
    id: uuid.UUID
    nombre: str
    correo: str
    rol: RolUsuario
    doctores_asignados: list[uuid.UUID]


# ---------- Doctor ----------
class DoctorCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    telefono_whatsapp: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    zona_horaria: str = "America/Mexico_City"
    hora_cierre_diario: time = time(20, 0)
    duracion_cita_default_min: int = Field(default=30, ge=5, le=480)
    activo: bool = True

    _zona = field_validator("zona_horaria")(_validar_zona)


class DoctorActualizar(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    telefono_whatsapp: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    zona_horaria: str | None = None
    hora_cierre_diario: time | None = None
    duracion_cita_default_min: int | None = Field(default=None, ge=5, le=480)
    activo: bool | None = None

    _zona = field_validator("zona_horaria")(_validar_zona)


class DoctorSalida(_Salida):
    id: uuid.UUID
    nombre: str
    telefono_whatsapp: str
    zona_horaria: str
    hora_cierre_diario: time
    duracion_cita_default_min: int
    activo: bool
    google_calendar_conectado: bool = False


# ---------- Paciente ----------
class PacienteCrear(BaseModel):
    nombre_completo: str = Field(min_length=1, max_length=200)
    telefono: str | None = Field(default=None, max_length=20)
    correo: str | None = Field(default=None, max_length=200)
    notas_clinicas_breves: str | None = Field(default=None, max_length=4000)


class PacienteActualizar(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=200)
    telefono: str | None = Field(default=None, max_length=20)
    correo: str | None = Field(default=None, max_length=200)
    notas_clinicas_breves: str | None = Field(default=None, max_length=4000)


class PacienteResumen(_Salida):
    id: uuid.UUID
    nombre_completo: str
    telefono: str | None


class PacienteSalida(PacienteResumen):
    correo: str | None
    notas_clinicas_breves: str | None


# ---------- Cita ----------
class CitaCrear(BaseModel):
    id_doctor: uuid.UUID
    id_paciente: uuid.UUID
    fecha_hora_inicio: AwareDatetime
    fecha_hora_fin: AwareDatetime | None = None
    duracion_minutos: int | None = Field(default=None, ge=5, le=480)
    motivo_consulta: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _rango(self) -> "CitaCrear":
        if self.fecha_hora_fin is not None and self.fecha_hora_fin <= self.fecha_hora_inicio:
            raise ValueError("fecha_hora_fin debe ser posterior a fecha_hora_inicio")
        return self


class CitaActualizar(BaseModel):
    fecha_hora_inicio: AwareDatetime | None = None
    fecha_hora_fin: AwareDatetime | None = None
    motivo_consulta: str | None = Field(default=None, max_length=2000)
    estado: EstadoCita | None = None
    estado_seguimiento: EstadoSeguimiento | None = None


class CitaSalida(_Salida):
    id: uuid.UUID
    id_doctor: uuid.UUID
    id_paciente: uuid.UUID
    paciente: PacienteResumen
    fecha_hora_inicio: datetime
    fecha_hora_fin: datetime
    motivo_consulta: str | None
    estado: EstadoCita
    estado_seguimiento: EstadoSeguimiento
    origen: OrigenCita
    estado_sync_google: EstadoSyncGoogle


class HorarioOcupadoSalida(BaseModel):
    detail: str = "horario ocupado"
    alternativas: list[datetime]


# ---------- Alertas ----------
class AlertaSalida(_Salida):
    id: uuid.UUID
    id_doctor: uuid.UUID
    nombre_doctor: str
    mensaje_ia: str
    instruccion_original: str
    estado: EstadoAlerta
    resuelta_por: uuid.UUID | None
    resuelta_en: datetime | None
    creado_en: datetime


# ---------- Dashboard ----------
class KpisSalida(BaseModel):
    citas_de_hoy: int
    en_espera: int
    atendidos: int
    alertas_pendientes: int
