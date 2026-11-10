"""Declaraciones de tools para Function Calling (IA-06..IA-11)."""

from typing import Any

_ISO = "Fecha y hora ISO 8601 con offset de la zona del doctor, ej. 2026-11-12T17:00:00-06:00."


def _tool(nombre: str, descripcion: str, props: dict[str, Any], req: list[str]) -> dict[str, Any]:
    return {
        "name": nombre,
        "description": descripcion,
        "parameters_json_schema": {"type": "object", "properties": props, "required": req},
    }


DECLARACIONES: list[dict[str, Any]] = [
    _tool(
        "buscar_paciente",
        "Busca pacientes existentes por nombre. Devuelve 0, 1 o varias coincidencias.",
        {"nombre": {"type": "string", "description": "Nombre o parte del nombre del paciente."}},
        ["nombre"],
    ),
    _tool(
        "consultar_disponibilidad",
        "Devuelve los horarios libres del doctor en una fecha.",
        {
            "fecha": {"type": "string", "description": "Fecha local del doctor, AAAA-MM-DD."},
            "duracion_minutos": {"type": "integer", "description": "Duracion de la cita."},
        },
        ["fecha"],
    ),
    _tool(
        "agendar_cita",
        "Crea una cita. Usa id_paciente si el paciente existe (coincidencia unica de "
        "buscar_paciente) o nombre_paciente_nuevo si el doctor indica que es paciente nuevo. "
        "Nunca ambos. Si el horario esta ocupado devuelve alternativas.",
        {
            "id_paciente": {"type": "string", "description": "ID devuelto por buscar_paciente."},
            "nombre_paciente_nuevo": {
                "type": "string",
                "description": "Nombre completo de un paciente que aun no existe.",
            },
            "fecha_hora_iso": {"type": "string", "description": _ISO},
            "duracion_minutos": {"type": "integer", "description": "Si se omite, la default."},
            "motivo": {"type": "string", "description": "Motivo de la consulta, si se dijo."},
        },
        ["fecha_hora_iso"],
    ),
    _tool(
        "crear_recordatorio_tarea",
        "Crea un recordatorio que se enviara al doctor por WhatsApp a la hora indicada.",
        {
            "fecha_hora_iso": {"type": "string", "description": _ISO},
            "descripcion_tarea": {"type": "string", "description": "Que hay que recordar."},
        },
        ["fecha_hora_iso", "descripcion_tarea"],
    ),
    _tool(
        "delegar_a_recepcion",
        "Crea una alerta para que recepcion ejecute la instruccion. Obligatorio para "
        "cancelaciones, reprogramaciones, varias coincidencias de paciente sin resolver y "
        "cualquier accion que implique contactar al paciente.",
        {
            "instruccion_literal": {
                "type": "string",
                "description": "La instruccion del doctor, textual y completa.",
            }
        },
        ["instruccion_literal"],
    ),
    _tool(
        "solicitar_aclaracion",
        "Hace una pregunta al doctor por WhatsApp y espera su respuesta. Usala ante cualquier "
        "duda (fecha, hora o paciente ambiguos).",
        {"pregunta": {"type": "string", "description": "Pregunta breve y concreta."}},
        ["pregunta"],
    ),
]
