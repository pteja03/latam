"""DAT-09 LogAuditoria (append-only)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LogAuditoria(Base):
    __tablename__ = "log_auditoria"
    __table_args__ = (Index("ix_log_auditoria_entidad", "entidad", "id_entidad"),)

    entidad: Mapped[str] = mapped_column(String(50))
    id_entidad: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    accion: Mapped[str] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(100))  # usuario:<id> | ia:<doctor_id> | sistema
    cambios: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # sin campos cifrados
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
