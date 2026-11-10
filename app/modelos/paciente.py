"""DAT-02 Paciente."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.tipos import TextoCifrado


class Paciente(Base):
    __tablename__ = "paciente"

    nombre_completo: Mapped[str] = mapped_column(String(200))
    # Minusculas, sin acentos, en claro: unico campo buscable del paciente.
    nombre_normalizado: Mapped[str] = mapped_column(String(200), index=True)
    telefono: Mapped[str | None] = mapped_column(String(20), default=None)
    correo: Mapped[str | None] = mapped_column(String(200), default=None)
    notas_clinicas_breves: Mapped[str | None] = mapped_column(TextoCifrado, default=None)
