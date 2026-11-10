"""DAT-03 Cita y DAT-05 antisolapamiento por constraint de exclusion."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.tipos import TextoCifrado
from app.modelos.doctor import Doctor
from app.modelos.enums import (
    EstadoCita,
    EstadoSeguimiento,
    EstadoSyncGoogle,
    OrigenCita,
    columna_enum,
)
from app.modelos.paciente import Paciente

NOMBRE_CONSTRAINT_SOLAPE = "excl_cita_solapada"


class Cita(Base):
    __tablename__ = "cita"

    id_doctor: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctor.id"))
    id_paciente: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id"), index=True)
    fecha_hora_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_hora_fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    motivo_consulta: Mapped[str | None] = mapped_column(TextoCifrado, default=None)
    estado: Mapped[EstadoCita] = mapped_column(
        columna_enum(EstadoCita), default=EstadoCita.PROGRAMADA
    )
    estado_seguimiento: Mapped[EstadoSeguimiento] = mapped_column(
        columna_enum(EstadoSeguimiento), default=EstadoSeguimiento.NINGUNO
    )
    origen: Mapped[OrigenCita] = mapped_column(columna_enum(OrigenCita))
    id_evento_google: Mapped[str | None] = mapped_column(String(255), default=None)
    estado_sync_google: Mapped[EstadoSyncGoogle] = mapped_column(
        columna_enum(EstadoSyncGoogle), default=EstadoSyncGoogle.PENDIENTE
    )

    doctor: Mapped[Doctor] = relationship(lazy="raise")
    paciente: Mapped[Paciente] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("fecha_hora_fin > fecha_hora_inicio", name="ck_cita_rango_valido"),
        ExcludeConstraint(
            ("id_doctor", "="),
            (func.tstzrange(text("fecha_hora_inicio"), text("fecha_hora_fin")), "&&"),
            where=text("estado <> 'cancelada' AND eliminado_en IS NULL"),
            using="gist",
            name=NOMBRE_CONSTRAINT_SOLAPE,
        ),
        Index("ix_cita_doctor_inicio", "id_doctor", "fecha_hora_inicio"),
    )
