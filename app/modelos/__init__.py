"""Modelos SQLAlchemy. Importarlos aqui los registra en Base.metadata."""

from app.modelos.alerta_recepcion import AlertaRecepcion
from app.modelos.cita import Cita
from app.modelos.doctor import Doctor
from app.modelos.log_auditoria import LogAuditoria
from app.modelos.paciente import Paciente
from app.modelos.recordatorio import Recordatorio
from app.modelos.usuario_recepcion import UsuarioRecepcion

__all__ = [
    "AlertaRecepcion",
    "Cita",
    "Doctor",
    "LogAuditoria",
    "Paciente",
    "Recordatorio",
    "UsuarioRecepcion",
]
