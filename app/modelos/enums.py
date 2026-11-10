"""Enums del dominio (DAT-04 y estados de otras entidades)."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class EstadoCita(StrEnum):
    PROGRAMADA = "programada"
    CONFIRMADA = "confirmada"
    EN_ESPERA = "en_espera"
    EN_CONSULTA = "en_consulta"
    ATENDIDA = "atendida"
    CANCELADA = "cancelada"
    NO_ASISTIO = "no_asistio"


class EstadoSeguimiento(StrEnum):
    NINGUNO = "ninguno"
    REQUIERE_SEGUIMIENTO = "requiere_seguimiento"
    SEGUIMIENTO_AGENDADO = "seguimiento_agendado"


class OrigenCita(StrEnum):
    IA = "ia"
    RECEPCION = "recepcion"


class EstadoSyncGoogle(StrEnum):
    PENDIENTE = "pendiente"
    SINCRONIZADO = "sincronizado"
    ERROR = "error"


class EstadoRecordatorio(StrEnum):
    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    CANCELADO = "cancelado"


class EstadoAlerta(StrEnum):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    RESUELTA = "resuelta"


class RolUsuario(StrEnum):
    RECEPCION = "recepcion"
    ADMIN = "admin"


def columna_enum(enum: type[StrEnum]) -> SAEnum:
    """Enum guardado como VARCHAR con sus valores (no nombres)."""
    return SAEnum(
        enum,
        native_enum=False,
        length=30,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
