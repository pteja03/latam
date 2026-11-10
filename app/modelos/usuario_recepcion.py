"""DAT-08 UsuarioRecepcion."""

import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modelos.enums import RolUsuario, columna_enum


class UsuarioRecepcion(Base):
    __tablename__ = "usuario_recepcion"
    __table_args__ = (
        Index(
            "uq_usuario_recepcion_correo",
            "correo",
            unique=True,
            postgresql_where="eliminado_en IS NULL",
        ),
    )

    nombre: Mapped[str] = mapped_column(String(200))
    correo: Mapped[str] = mapped_column(String(200))
    hash_password: Mapped[str] = mapped_column(String(255))
    rol: Mapped[RolUsuario] = mapped_column(columna_enum(RolUsuario), default=RolUsuario.RECEPCION)
    # Doctores cuya agenda puede ver/gestionar. El rol admin ve todos.
    doctores_asignados: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
