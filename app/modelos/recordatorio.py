"""DAT-06 Recordatorio."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.tipos import TextoCifrado
from app.modelos.enums import EstadoRecordatorio, columna_enum


class Recordatorio(Base):
    __tablename__ = "recordatorio"
    __table_args__ = (Index("ix_recordatorio_estado_fecha", "estado", "fecha_hora"),)

    id_doctor: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctor.id"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Texto libre dictado por el doctor: puede contener datos de pacientes, se cifra.
    descripcion: Mapped[str] = mapped_column(TextoCifrado)
    estado: Mapped[EstadoRecordatorio] = mapped_column(
        columna_enum(EstadoRecordatorio), default=EstadoRecordatorio.PENDIENTE
    )
