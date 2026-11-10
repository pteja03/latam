"""DAT-07 AlertaRecepcion."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.tipos import TextoCifrado
from app.modelos.doctor import Doctor
from app.modelos.enums import EstadoAlerta, columna_enum


class AlertaRecepcion(Base):
    __tablename__ = "alerta_recepcion"
    __table_args__ = (Index("ix_alerta_doctor_estado", "id_doctor", "estado"),)

    id_doctor: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctor.id"))
    # Ambos textos pueden contener datos de pacientes: se cifran.
    mensaje_ia: Mapped[str] = mapped_column(TextoCifrado)
    instruccion_original: Mapped[str] = mapped_column(TextoCifrado)
    estado: Mapped[EstadoAlerta] = mapped_column(
        columna_enum(EstadoAlerta), default=EstadoAlerta.PENDIENTE
    )
    resuelta_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_recepcion.id"), default=None
    )
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    doctor: Mapped[Doctor] = relationship(lazy="raise")
