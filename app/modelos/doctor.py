"""DAT-01 Doctor."""

from datetime import time

from sqlalchemy import Boolean, Index, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.tipos import TextoCifrado


class Doctor(Base):
    __tablename__ = "doctor"
    __table_args__ = (
        Index(
            "uq_doctor_telefono_whatsapp",
            "telefono_whatsapp",
            unique=True,
            postgresql_where="eliminado_en IS NULL",
        ),
    )

    nombre: Mapped[str] = mapped_column(String(200))
    telefono_whatsapp: Mapped[str] = mapped_column(String(20))  # E.164
    zona_horaria: Mapped[str] = mapped_column(String(64), default="America/Mexico_City")  # IANA
    hora_cierre_diario: Mapped[time] = mapped_column(Time, default=time(20, 0))  # hora local
    duracion_cita_default_min: Mapped[int] = mapped_column(Integer, default=30)
    credenciales_google_calendar: Mapped[str | None] = mapped_column(TextoCifrado, default=None)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
