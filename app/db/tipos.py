"""Tipos de columna cifrados (SEG-01). Los campos cifrados no son buscables."""

from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.cifrado import cifrar, descifrar


class TextoCifrado(TypeDecorator[str]):
    """Guarda el texto cifrado con MultiFernet; lo descifra al leer."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else cifrar(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else descifrar(value)
