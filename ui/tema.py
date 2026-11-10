"""Tema visual de recepcion (UI-01). Estilo HIS: sobrio, sin estetica comercial."""

import flet as ft

FONDO = "#F8FAFC"
TARJETA = "#FFFFFF"
PRIMARIO = "#0369A1"
ACENTO = "#0F766E"
TEXTO = "#1E293B"
TEXTO_SUAVE = "#64748B"
TEXTO_TENUE = "#94A3B8"
BORDE = "#E2E8F0"
PELIGRO = "#B91C1C"
AVISO = "#B45309"

# Color por estado de cita (DAT-04). El badge usa el color al 12 % de opacidad.
ESTADOS: dict[str, tuple[str, str]] = {
    "programada": ("Programada", PRIMARIO),
    "confirmada": ("Confirmada", ACENTO),
    "en_espera": ("En espera", AVISO),
    "en_consulta": ("En consulta", "#6D28D9"),
    "atendida": ("Atendida", "#15803D"),
    "cancelada": ("Cancelada", TEXTO_SUAVE),
    "no_asistio": ("No asistió", PELIGRO),
}
ESTADOS_ALERTA: dict[str, tuple[str, str]] = {
    "pendiente": ("Pendiente", AVISO),
    "en_proceso": ("En proceso", PRIMARIO),
    "resuelta": ("Resuelta", "#15803D"),
}


def tema() -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=PRIMARIO,
        color_scheme=ft.ColorScheme(
            primary=PRIMARIO, secondary=ACENTO, surface=TARJETA, on_surface=TEXTO, error=PELIGRO
        ),
        scaffold_bgcolor=FONDO,
    )


def texto(
    valor: str,
    tam: float = 14,
    peso: ft.FontWeight = ft.FontWeight.W_400,
    color: str = TEXTO,
    **extra: object,
) -> ft.Text:
    return ft.Text(valor, size=tam, weight=peso, color=color, **extra)


def titulo(valor: str, tam: float = 20) -> ft.Text:
    return texto(valor, tam, ft.FontWeight.W_600)


def etiqueta(valor: str) -> ft.Text:
    """Rotulo pequeno en mayusculas para secciones y campos."""
    return ft.Text(
        valor.upper(),
        size=11,
        weight=ft.FontWeight.W_600,
        color=TEXTO_SUAVE,
        style=ft.TextStyle(letter_spacing=0.6),
    )


def tarjeta(contenido: ft.Control, relleno: float = 20, **extra: object) -> ft.Container:
    return ft.Container(
        content=contenido,
        padding=relleno,
        bgcolor=TARJETA,
        border=ft.Border.all(1, BORDE),
        border_radius=12,
        **extra,
    )


def badge(rotulo: str, color: str) -> ft.Container:
    """Badge translucido de estado (UI-05)."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=6, height=6, bgcolor=color, border_radius=3),
                ft.Text(rotulo, size=12, weight=ft.FontWeight.W_600, color=color),
            ],
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        bgcolor=ft.Colors.with_opacity(0.12, color),
        border_radius=999,
    )


def badge_estado(estado: str) -> ft.Container:
    rotulo, color = ESTADOS.get(estado, (estado, TEXTO_SUAVE))
    return badge(rotulo, color)


def boton_primario(rotulo: str, al_pulsar: object, **extra: object) -> ft.FilledButton:
    return ft.FilledButton(
        content=rotulo,
        on_click=al_pulsar,
        style=ft.ButtonStyle(
            bgcolor=PRIMARIO,
            color="#FFFFFF",
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        ),
        **extra,
    )


def boton_secundario(rotulo: str, al_pulsar: object, color: str = PRIMARIO, **extra: object):
    return ft.OutlinedButton(
        content=rotulo,
        on_click=al_pulsar,
        style=ft.ButtonStyle(
            color=color,
            side=ft.BorderSide(1, BORDE),
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        ),
        **extra,
    )


def borde_campo() -> dict[ft.ControlState, ft.OutlineInputBorder]:
    def contorno(color: str, ancho: float) -> ft.OutlineInputBorder:
        return ft.OutlineInputBorder(
            side=ft.BorderSide(ancho, color), border_radius=ft.BorderRadius.all(8)
        )

    return {
        ft.ControlState.DEFAULT: contorno(BORDE, 1),
        ft.ControlState.FOCUSED: contorno(PRIMARIO, 1.5),
        ft.ControlState.ERROR: contorno(PELIGRO, 1),
    }


def campo(rotulo: str, **extra: object) -> ft.TextField:
    return ft.TextField(
        label=rotulo,
        border=borde_campo(),
        text_size=14,
        dense=True,
        bgcolor=TARJETA,
        **extra,
    )
