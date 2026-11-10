"""Componentes de la UI de recepcion: KPIs, tarjetas de paciente, alertas y calendario."""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft

from ui import tema

HORA_INICIO = 8
HORA_FIN = 20
ALTO_INTERVALO = {15: 30, 30: 44}  # px por intervalo (UI-07)
ANCHO_HORAS = 60
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

AlPulsar = Callable[[dict[str, Any]], Any]


# ---------- fechas (UI-08: siempre en la zona del doctor) ----------
def en_zona(iso: str, zona: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(zona))


def hora(iso: str, zona: str) -> str:
    return en_zona(iso, zona).strftime("%H:%M")


def rango(cita: dict[str, Any], zona: str) -> str:
    return f"{hora(cita['fecha_hora_inicio'], zona)} – {hora(cita['fecha_hora_fin'], zona)}"


def fecha_larga(dia: date) -> str:
    return f"{_DIAS[dia.weekday()].capitalize()} {dia.day} de {_MESES[dia.month - 1]} {dia.year}"


def abreviatura_zona(zona: str, dia: date) -> str:
    momento = datetime.combine(dia, time(12), tzinfo=ZoneInfo(zona))
    desfase = momento.utcoffset() or timedelta()
    horas = int(desfase.total_seconds() // 3600)
    return f"{zona.split('/')[-1].replace('_', ' ')} · UTC{horas:+d}"


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p[0].isalpha()]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


# ---------- KPIs (UI-03) ----------
def kpi(rotulo: str, valor: int, icono: str, color: str) -> ft.Container:
    return tema.tarjeta(
        ft.Row(
            [
                ft.Column(
                    [
                        tema.etiqueta(rotulo),
                        tema.texto(str(valor), 34, ft.FontWeight.W_600),
                    ],
                    spacing=6,
                    tight=True,
                ),
                ft.Container(
                    content=ft.Icon(icono, color=color, size=22),
                    width=44,
                    height=44,
                    bgcolor=ft.Colors.with_opacity(0.10, color),
                    border_radius=10,
                    alignment=ft.Alignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        expand=True,
    )


# ---------- tarjeta de paciente horizontal (UI-05) ----------
def tarjeta_cita(
    cita: dict[str, Any], doctor: dict[str, Any], al_pulsar: AlPulsar, seleccionada: bool
) -> ft.Container:
    zona = doctor["zona_horaria"]
    nombre = cita["paciente"]["nombre_completo"]
    _, color = tema.ESTADOS.get(cita["estado"], ("", tema.TEXTO_SUAVE))
    apagada = cita["estado"] in ("cancelada", "no_asistio")
    return ft.Container(
        content=ft.Row(
            [
                ft.Container(width=4, height=44, bgcolor=color, border_radius=2),
                ft.Column(
                    [
                        tema.texto(hora(cita["fecha_hora_inicio"], zona), 16, ft.FontWeight.W_600),
                        tema.texto(hora(cita["fecha_hora_fin"], zona), 12, color=tema.TEXTO_SUAVE),
                    ],
                    spacing=0,
                    width=58,
                    tight=True,
                ),
                ft.Container(
                    content=tema.texto(iniciales(nombre), 13, ft.FontWeight.W_600, tema.PRIMARIO),
                    width=38,
                    height=38,
                    bgcolor=ft.Colors.with_opacity(0.08, tema.PRIMARIO),
                    border_radius=19,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        tema.texto(
                            nombre,
                            15,
                            ft.FontWeight.W_600,
                            tema.TEXTO_SUAVE if apagada else tema.TEXTO,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        tema.texto(
                            doctor["nombre"]
                            + (" · agendada por IA" if cita["origen"] == "ia" else ""),
                            12,
                            color=tema.TEXTO_SUAVE,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                    tight=True,
                ),
                tema.badge_estado(cita["estado"]),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=tema.TEXTO_TENUE, size=20),
            ],
            spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        bgcolor=tema.TARJETA,
        border=ft.Border.all(
            1.5 if seleccionada else 1, tema.PRIMARIO if seleccionada else tema.BORDE
        ),
        border_radius=12,
        ink=True,
        on_click=lambda _: al_pulsar(cita),
    )


# ---------- alerta IA (UI-04) ----------
def tarjeta_alerta(
    alerta: dict[str, Any], zona: str, al_tomar: AlPulsar, al_resolver: AlPulsar
) -> ft.Container:
    rotulo, color = tema.ESTADOS_ALERTA[alerta["estado"]]
    creada = en_zona(alerta["creado_en"], zona)
    acciones: list[ft.Control] = []
    if alerta["estado"] == "pendiente":
        acciones.append(tema.boton_secundario("Tomar", lambda _: al_tomar(alerta)))
    if alerta["estado"] != "resuelta":
        acciones.append(tema.boton_primario("Resolver", lambda _: al_resolver(alerta)))
    return tema.tarjeta(
        ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=tema.ACENTO, size=18),
                        tema.texto(alerta["nombre_doctor"], 14, ft.FontWeight.W_600),
                        tema.texto(
                            f"{creada.day} {_MESES[creada.month - 1]} · {creada:%H:%M}",
                            12,
                            color=tema.TEXTO_SUAVE,
                        ),
                        ft.Container(expand=True),
                        tema.badge(rotulo, color),
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                tema.etiqueta("Instrucción original del doctor"),
                ft.Container(
                    content=tema.texto(f"“{alerta['instruccion_original']}”", 15, selectable=True),
                    padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                    bgcolor=tema.FONDO,
                    border=ft.Border.only(left=ft.BorderSide(3, tema.ACENTO)),
                    border_radius=6,
                ),
                ft.Row(
                    [
                        ft.Container(
                            tema.texto(alerta["mensaje_ia"], 13, color=tema.TEXTO_SUAVE),
                            expand=True,
                        ),
                        *acciones,
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=12,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


# ---------- calendario time-blocking por columnas (UI-07, UI-08) ----------
def _bloque(
    cita: dict[str, Any], zona: str, dia: date, intervalo: int, al_pulsar: AlPulsar, activa: bool
) -> ft.Container | None:
    alto = ALTO_INTERVALO[intervalo]
    inicio = en_zona(cita["fecha_hora_inicio"], zona)
    fin = en_zona(cita["fecha_hora_fin"], zona)
    apertura = datetime.combine(dia, time(HORA_INICIO), tzinfo=inicio.tzinfo)
    cierre = datetime.combine(dia, time(HORA_FIN), tzinfo=inicio.tzinfo)
    inicio_v, fin_v = max(inicio, apertura), min(fin, cierre)
    if fin_v <= inicio_v:
        return None
    minutos_desde = (inicio_v - apertura).total_seconds() / 60
    duracion = (fin_v - inicio_v).total_seconds() / 60
    alto_px = max(duracion / intervalo * alto - 3, 20)
    _, color = tema.ESTADOS.get(cita["estado"], ("", tema.TEXTO_SUAVE))
    lineas: list[ft.Control] = [
        tema.texto(
            cita["paciente"]["nombre_completo"],
            13,
            ft.FontWeight.W_600,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
    ]
    if alto_px >= 38:
        lineas.append(tema.texto(rango(cita, zona), 11, color=tema.TEXTO_SUAVE, max_lines=1))
    return ft.Container(
        content=ft.Column(lineas, spacing=0, tight=True),
        top=minutos_desde / intervalo * alto + 1,
        left=4,
        right=6,
        height=alto_px,
        padding=ft.Padding.only(left=10, right=6, top=3),
        bgcolor=ft.Colors.with_opacity(0.22 if activa else 0.12, color),
        border=ft.Border.only(left=ft.BorderSide(3, color)),
        border_radius=6,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        ink=True,
        tooltip=f"{cita['paciente']['nombre_completo']} · {rango(cita, zona)}",
        on_click=lambda _: al_pulsar(cita),
    )


def calendario(
    doctores: list[dict[str, Any]],
    citas: list[dict[str, Any]],
    dia: date,
    intervalo: int,
    al_pulsar: AlPulsar,
    id_seleccionada: str | None,
) -> ft.Control:
    alto = ALTO_INTERVALO[intervalo]
    por_hora = 60 // intervalo
    total = (HORA_FIN - HORA_INICIO) * por_hora
    alto_total = total * alto

    def lineas() -> list[ft.Control]:
        return [
            ft.Container(
                top=i * alto,
                left=0,
                right=0,
                height=1,
                bgcolor=tema.BORDE if i % por_hora == 0 else "#F1F5F9",
            )
            for i in range(total + 1)
        ]

    columna_horas = ft.Stack(
        [
            ft.Container(
                content=tema.texto(f"{HORA_INICIO + h:02d}:00", 11, color=tema.TEXTO_SUAVE),
                top=max(h * por_hora * alto - 7, 0),
                right=10,
            )
            for h in range(HORA_FIN - HORA_INICIO + 1)
        ],
        width=ANCHO_HORAS,
        height=alto_total + 8,
    )

    encabezados: list[ft.Control] = [ft.Container(width=ANCHO_HORAS)]
    columnas: list[ft.Control] = [columna_horas]
    for doctor in doctores:
        zona = doctor["zona_horaria"]
        del_doctor = [
            c for c in citas if c["id_doctor"] == doctor["id"] and c["estado"] != "cancelada"
        ]
        bloques = [
            b
            for c in del_doctor
            if en_zona(c["fecha_hora_inicio"], zona).date() == dia
            and (b := _bloque(c, zona, dia, intervalo, al_pulsar, c["id"] == id_seleccionada))
        ]
        encabezados.append(
            ft.Container(
                content=ft.Column(
                    [
                        tema.texto(doctor["nombre"], 14, ft.FontWeight.W_600, max_lines=1),
                        tema.texto(
                            f"{abreviatura_zona(zona, dia)} · {len(bloques)} citas",
                            11,
                            color=tema.TEXTO_SUAVE,
                        ),
                    ],
                    spacing=2,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                border=ft.Border.only(left=ft.BorderSide(1, tema.BORDE)),
                expand=True,
            )
        )
        columnas.append(
            ft.Container(
                content=ft.Stack([*lineas(), *bloques], height=alto_total + 8),
                border=ft.Border.only(left=ft.BorderSide(1, tema.BORDE)),
                expand=True,
            )
        )
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    ft.Row(encabezados, spacing=0),
                    border=ft.Border.only(bottom=ft.BorderSide(1, tema.BORDE)),
                ),
                ft.Column(
                    [
                        ft.Container(
                            ft.Row(
                                columnas,
                                spacing=0,
                                vertical_alignment=ft.CrossAxisAlignment.START,
                            ),
                            padding=ft.Padding.only(top=10, bottom=6),
                        )
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            ],
            spacing=0,
        ),
        bgcolor=tema.TARJETA,
        border=ft.Border.all(1, tema.BORDE),
        border_radius=12,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        expand=True,
    )
