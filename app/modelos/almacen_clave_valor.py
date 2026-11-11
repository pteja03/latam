"""ARQ-08 Almacen clave-valor con caducidad: sustituye a Redis en la instalacion local."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlmacenClaveValor(Base):
    __tablename__ = "almacen_clave_valor"
    __table_args__ = (Index("uq_almacen_clave", "clave", unique=True),)

    clave: Mapped[str] = mapped_column(String(200))
    # JSON cifrado: el historial de chat contiene texto dictado por el doctor.
    valor: Mapped[str] = mapped_column(Text)
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
