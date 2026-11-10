"""ARQ-05 UI de recepcion (Flet, escritorio y web). Consume api_core por HTTP con token.

python -m ui.main            # web en http://localhost:8550
UI_MODO=escritorio python -m ui.main
"""

import asyncio
import os
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft

from ui import componentes as comp
from ui import tema
from ui.api import ClienteApi, ErrorApi, SesionExpirada

SEGUNDOS_POLLING = int(os.environ.get("UI_POLLING_SEG", "30"))  # UI-09
ANCHO_PANEL = 360

_TRANSICIONES: list[tuple[str, str]] = [
    ("confirmada", "Confirmar"),
    ("en_espera", "Llegó · en espera"),
    ("en_consulta", "Pasar a consulta"),
    ("atendida", "Marcar atendida"),
    ("no_asistio", "No asistió"),
    ("cancelada", "Cancelar cita"),
]


class AppRecepcion:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.api = ClienteApi()
        self.usuario: dict[str, Any] | None = None
        self.doctores: list[dict[str, Any]] = []
        self.citas: list[dict[str, Any]] = []
        self.alertas: list[dict[str, Any]] = []
        self.kpis: dict[str, int] = {}
        self.vista = "dashboard"
        self.id_doctor: str | None = None  # filtro por doctor (UI-03)
        self.dia = date.today()
        self.intervalo = 30
        self.cita_sel: dict[str, Any] | None = None
        self.paciente_sel: dict[str, Any] | None = None
        self.actualizado: datetime | None = None
        self._huella: Any = None
        self._sondeo_activo = False

    # ================= ciclo de vida =================
    def iniciar(self) -> None:
        page = self.page
        page.title = "Clínica CREE · Agenda médica"
        page.theme = tema.tema()
        page.theme_mode = ft.ThemeMode.LIGHT
        page.bgcolor = tema.FONDO
        page.padding = 0
        self._mostrar_login()

    def _aviso(self, mensaje: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(mensaje, color="#FFFFFF"),
                bgcolor=tema.PELIGRO if error else tema.TEXTO,
            )
        )

    async def _seguro(self, corrutina: Any) -> Any:
        """Ejecuta una llamada a la API mostrando errores sin tumbar la UI."""
        try:
            return await corrutina
        except SesionExpirada:
            self._cerrar_sesion()
            self._aviso("Tu sesión expiró. Vuelve a iniciar sesión.", error=True)
        except ErrorApi as error:
            self._aviso(error.detalle, error=True)
        return None

    # ================= login (UI-02) =================
    def _mostrar_login(self, mensaje: str | None = None) -> None:
        correo = tema.campo("Correo", autofocus=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        password = tema.campo(
            "Contraseña",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
        )
        error = tema.texto(mensaje or "", 13, color=tema.PELIGRO, visible=bool(mensaje))

        async def entrar(_: Any = None) -> None:
            if not correo.value or not password.value:
                error.value, error.visible = "Escribe tu correo y contraseña.", True
                self.page.update()
                return
            try:
                self.usuario = await self.api.login(correo.value.strip(), password.value)
            except ErrorApi as fallo:
                error.value, error.visible = fallo.detalle, True
                self.page.update()
                return
            await self.refrescar(forzar=True)
            if not self._sondeo_activo:
                self._sondeo_activo = True
                self.page.run_task(self._sondeo)

        password.on_submit = entrar
        correo.on_submit = entrar
        formulario = tema.tarjeta(
            ft.Column(
                [
                    _marca(grande=True),
                    ft.Container(height=4),
                    tema.titulo("Acceso de recepción", 22),
                    tema.texto(
                        "Agenda médica de la Clínica CREE. Ingresa con tu cuenta de recepción.",
                        13,
                        color=tema.TEXTO_SUAVE,
                    ),
                    ft.Container(height=8),
                    correo,
                    password,
                    error,
                    ft.Container(height=4),
                    ft.Row([tema.boton_primario("Iniciar sesión", entrar, expand=True)]),
                ],
                spacing=12,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            relleno=36,
            width=420,
            shadow=ft.BoxShadow(
                blur_radius=32,
                color=ft.Colors.with_opacity(0.08, tema.TEXTO),
                offset=ft.Offset(0, 8),
            ),
        )
        self.page.controls = [
            ft.Container(
                content=ft.Column(
                    [
                        formulario,
                        tema.texto(
                            "Uso exclusivo del personal autorizado. La actividad queda registrada.",
                            12,
                            color=tema.TEXTO_TENUE,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=20,
                ),
                alignment=ft.Alignment.CENTER,
                expand=True,
                bgcolor=tema.FONDO,
            )
        ]
        self.page.update()

    def _cerrar_sesion(self, _: Any = None) -> None:
        self.api.cerrar_sesion()
        self.usuario = None
        self.cita_sel = self.paciente_sel = None
        self._huella = None
        self._mostrar_login()

    # ================= datos =================
    def _doctores_visibles(self) -> list[dict[str, Any]]:
        activos = [d for d in self.doctores if d["activo"]]
        return [d for d in activos if self.id_doctor in (None, d["id"])]

    def _doctor(self, id_doctor: str) -> dict[str, Any] | None:
        return next((d for d in self.doctores if d["id"] == id_doctor), None)

    def _hoy(self, doctor: dict[str, Any]) -> date:
        return datetime.now(ZoneInfo(doctor["zona_horaria"])).date()

    async def refrescar(self, forzar: bool = False) -> None:
        if not self.api.autenticado:
            return
        primero, ultimo = min(self.dia, date.today()), max(self.dia, date.today())
        desde = datetime.combine(primero - timedelta(days=1), time.min, tzinfo=UTC)
        hasta = datetime.combine(ultimo + timedelta(days=2), time.min, tzinfo=UTC)
        datos = await self._seguro(
            asyncio.gather(
                self.api.doctores(),
                self.api.citas(desde.isoformat(), hasta.isoformat()),
                self.api.alertas(),
                self.api.kpis(self.id_doctor),
            )
        )
        if datos is None:
            return
        self.doctores, self.citas, self.alertas, self.kpis = datos
        self.actualizado = datetime.now()
        if self.cita_sel:
            self.cita_sel = next((c for c in self.citas if c["id"] == self.cita_sel["id"]), None)
        huella = (datos, self.vista, self.id_doctor, self.dia, self.intervalo)
        if forzar or huella != self._huella:  # sin cambios no se redibuja (conserva el scroll)
            self._huella = huella
            self._dibujar()

    async def _sondeo(self) -> None:
        """UI-09: polling periodico."""
        while True:
            await asyncio.sleep(SEGUNDOS_POLLING)
            if self.api.autenticado:
                await self.refrescar()

    # ================= acciones =================
    async def _ir(self, vista: str) -> None:
        self.vista = vista
        await self.refrescar(forzar=True)

    async def _filtrar_doctor(self, evento: ft.Event[ft.Dropdown]) -> None:
        valor = evento.control.value
        self.id_doctor = None if valor in (None, "todos") else valor
        await self.refrescar(forzar=True)

    async def _mover_dia(self, dias: int | None) -> None:
        self.dia = date.today() if dias is None else self.dia + timedelta(days=dias)
        await self.refrescar(forzar=True)

    async def _cambiar_intervalo(self, evento: ft.Event[ft.SegmentedButton]) -> None:
        self.intervalo = int(next(iter(evento.control.selected)))
        self._dibujar()

    async def _abrir_cita(self, cita: dict[str, Any]) -> None:
        """UI-06: panel lateral de contexto, sin salir de la vista."""
        self.cita_sel = cita
        self.paciente_sel = None
        self._dibujar()
        self.paciente_sel = await self._seguro(self.api.paciente(cita["id_paciente"]))
        self._dibujar()

    def _cerrar_panel(self, _: Any = None) -> None:
        self.cita_sel = self.paciente_sel = None
        self._dibujar()

    async def _cambiar_estado(self, estado: str) -> None:
        if self.cita_sel is None:
            return
        if await self._seguro(self.api.cambiar_estado_cita(self.cita_sel["id"], estado)):
            await self.refrescar(forzar=True)

    async def _tomar(self, alerta: dict[str, Any]) -> None:
        if await self._seguro(self.api.tomar_alerta(alerta["id"])):
            await self.refrescar(forzar=True)

    async def _resolver(self, alerta: dict[str, Any]) -> None:
        if await self._seguro(self.api.resolver_alerta(alerta["id"])):
            self._aviso("Alerta resuelta")
            await self.refrescar(forzar=True)

    # ================= nueva cita =================
    def _dialogo_nueva_cita(self, _: Any = None) -> None:
        doctores = [d for d in self.doctores if d["activo"]]
        if not doctores:
            self._aviso("No hay doctores activos.", error=True)
            return
        inicial = self.id_doctor or doctores[0]["id"]
        doctor = ft.Dropdown(
            label="Doctor",
            value=inicial,
            options=[ft.DropdownOption(key=d["id"], text=d["nombre"]) for d in doctores],
            border=tema.borde_campo(),
            text_size=14,
            expand=True,
        )
        paciente = tema.campo(
            "Paciente (nombre completo)",
            helper="Si no existe, se registra como paciente nuevo.",
            autofocus=True,
        )
        telefono = tema.campo("Teléfono (solo paciente nuevo)")
        fecha = tema.campo("Fecha", value=self.dia.isoformat(), hint_text="AAAA-MM-DD", expand=True)
        hora = tema.campo("Hora", value="09:00", hint_text="HH:MM", expand=True)
        duracion = tema.campo(
            "Minutos", value=str(doctores[0]["duracion_cita_default_min"]), expand=True
        )
        motivo = tema.campo("Motivo de consulta", multiline=True, min_lines=2, max_lines=3)
        error = tema.texto("", 13, color=tema.PELIGRO, visible=False)

        def fallar(mensaje: str) -> None:
            error.value, error.visible = mensaje, True
            self.page.update()

        async def guardar(_: Any) -> None:
            elegido = self._doctor(doctor.value or "")
            nombre = " ".join((paciente.value or "").split())
            if elegido is None or len(nombre) < 3:
                return fallar("Indica el doctor y el nombre completo del paciente.")
            try:
                inicio = datetime.combine(
                    date.fromisoformat((fecha.value or "").strip()),
                    time.fromisoformat((hora.value or "").strip()),
                    tzinfo=ZoneInfo(elegido["zona_horaria"]),  # hora en la zona del doctor
                )
                minutos = int(duracion.value) if (duracion.value or "").strip() else None
            except ValueError:
                return fallar("Revisa la fecha (AAAA-MM-DD), la hora (HH:MM) y la duración.")
            try:
                encontrados = await self.api.buscar_pacientes(nombre)
                exactos = [
                    p for p in encontrados if p["nombre_completo"].casefold() == nombre.casefold()
                ]
                candidatos = exactos or encontrados
                if len(candidatos) > 1:
                    nombres = ", ".join(p["nombre_completo"] for p in candidatos[:4])
                    return fallar(
                        f"Hay varias coincidencias ({nombres}). Escribe el nombre exacto."
                    )
                elegido_p = (
                    candidatos[0]
                    if candidatos
                    else await self.api.crear_paciente(nombre, (telefono.value or "").strip())
                )
                await self.api.crear_cita(
                    {
                        "id_doctor": elegido["id"],
                        "id_paciente": elegido_p["id"],
                        "fecha_hora_inicio": inicio.isoformat(),
                        "duracion_minutos": minutos,
                        "motivo_consulta": (motivo.value or "").strip() or None,
                    }
                )
            except SesionExpirada:
                self.page.pop_dialog()
                self._cerrar_sesion()
                return None
            except ErrorApi as fallo:
                if fallo.estado == 409 and isinstance(fallo.cuerpo, dict):
                    libres = [
                        comp.hora(a, elegido["zona_horaria"])
                        for a in fallo.cuerpo.get("alternativas", [])
                    ]
                    sugerencia = (
                        f" Horarios libres cercanos: {', '.join(libres)}." if libres else ""
                    )
                    return fallar(f"Horario ocupado.{sugerencia}")
                return fallar(fallo.detalle)
            self.page.pop_dialog()
            self._aviso(f"Cita agendada para {elegido_p['nombre_completo']}")
            self.dia = inicio.date()
            await self.refrescar(forzar=True)
            return None

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=tema.TARJETA,
                shape=ft.RoundedRectangleBorder(radius=14),
                title=tema.titulo("Nueva cita", 18),
                content=ft.Container(
                    ft.Column(
                        [
                            ft.Row([doctor]),
                            paciente,
                            telefono,
                            ft.Row([fecha, hora, duracion], spacing=10),
                            motivo,
                            error,
                        ],
                        spacing=14,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    width=460,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    tema.boton_primario("Agendar", guardar),
                ],
            )
        )

    # ================= dibujo =================
    def _dibujar(self) -> None:
        if self.usuario is None:
            return
        cuerpo = {
            "dashboard": self._vista_dashboard,
            "agenda": self._vista_agenda,
            "alertas": self._vista_alertas,
        }[self.vista]()
        zona_principal = ft.Container(
            content=ft.Column([self._barra_superior(), cuerpo], spacing=20, expand=True),
            padding=ft.Padding.only(left=28, right=28, top=22, bottom=20),
            expand=True,
        )
        fila: list[ft.Control] = [self._barra_lateral(), zona_principal]
        if self.cita_sel is not None:
            fila.append(self._panel_contexto())
        self.page.controls = [ft.Row(fila, spacing=0, expand=True)]
        self.page.update()

    def _barra_lateral(self) -> ft.Container:
        pendientes = sum(1 for a in self.alertas if a["estado"] == "pendiente")

        def item(vista: str, rotulo: str, icono: str, contador: int = 0) -> ft.Container:
            activo = self.vista == vista
            color = tema.PRIMARIO if activo else tema.TEXTO_SUAVE
            fila: list[ft.Control] = [
                ft.Icon(icono, color=color, size=20),
                ft.Container(
                    tema.texto(
                        rotulo,
                        14,
                        ft.FontWeight.W_600 if activo else ft.FontWeight.W_500,
                        tema.PRIMARIO if activo else tema.TEXTO,
                    ),
                    expand=True,
                ),
            ]
            if contador:
                fila.append(
                    ft.Container(
                        tema.texto(str(contador), 11, ft.FontWeight.W_700, "#FFFFFF"),
                        bgcolor=tema.AVISO,
                        border_radius=999,
                        padding=ft.Padding.symmetric(horizontal=7, vertical=2),
                    )
                )

            async def ir(_: Any) -> None:
                await self._ir(vista)

            return ft.Container(
                content=ft.Row(fila, spacing=12),
                padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                bgcolor=ft.Colors.with_opacity(0.08, tema.PRIMARIO) if activo else None,
                border_radius=8,
                ink=True,
                on_click=ir,
            )

        assert self.usuario is not None
        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(_marca(), padding=ft.Padding.only(left=6, bottom=22, top=2)),
                    tema.etiqueta("  Recepción"),
                    item("dashboard", "Dashboard", ft.Icons.DASHBOARD_OUTLINED),
                    item("agenda", "Agenda", ft.Icons.CALENDAR_MONTH_OUTLINED),
                    item("alertas", "Alertas IA", ft.Icons.INBOX_OUTLINED, pendientes),
                    ft.Container(expand=True),
                    ft.Divider(height=1, color=tema.BORDE),
                    ft.Row(
                        [
                            ft.Container(
                                tema.texto(
                                    comp.iniciales(self.usuario["nombre"]),
                                    12,
                                    ft.FontWeight.W_600,
                                    tema.ACENTO,
                                ),
                                width=34,
                                height=34,
                                bgcolor=ft.Colors.with_opacity(0.10, tema.ACENTO),
                                border_radius=17,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column(
                                [
                                    tema.texto(
                                        self.usuario["nombre"],
                                        13,
                                        ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    tema.texto(
                                        "Administración"
                                        if self.usuario["rol"] == "admin"
                                        else "Recepción",
                                        11,
                                        color=tema.TEXTO_SUAVE,
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                                tight=True,
                            ),
                            ft.IconButton(
                                ft.Icons.LOGOUT,
                                icon_color=tema.TEXTO_SUAVE,
                                icon_size=18,
                                tooltip="Cerrar sesión",
                                on_click=self._cerrar_sesion,
                            ),
                        ],
                        spacing=10,
                    ),
                ],
                spacing=6,
            ),
            width=236,
            padding=ft.Padding.only(left=14, right=14, top=20, bottom=14),
            bgcolor=tema.TARJETA,
            border=ft.Border.only(right=ft.BorderSide(1, tema.BORDE)),
        )

    def _barra_superior(self) -> ft.Row:
        titulos = {
            "dashboard": ("Dashboard", comp.fecha_larga(date.today())),
            "agenda": ("Agenda", comp.fecha_larga(self.dia)),
            "alertas": ("Alertas IA", "Instrucciones que la IA delegó a recepción"),
        }
        principal, secundario = titulos[self.vista]
        opciones = [ft.DropdownOption(key="todos", text="Todos los doctores")] + [
            ft.DropdownOption(key=d["id"], text=d["nombre"]) for d in self.doctores if d["activo"]
        ]
        sello = f"Actualizado {self.actualizado:%H:%M:%S}" if self.actualizado else ""

        async def recargar(_: Any) -> None:
            await self.refrescar(forzar=True)

        return ft.Row(
            [
                ft.Column(
                    [
                        tema.titulo(principal, 24),
                        tema.texto(secundario, 13, color=tema.TEXTO_SUAVE),
                    ],
                    spacing=2,
                    expand=True,
                    tight=True,
                ),
                tema.texto(sello, 12, color=tema.TEXTO_TENUE),
                ft.IconButton(
                    ft.Icons.REFRESH,
                    icon_color=tema.TEXTO_SUAVE,
                    icon_size=18,
                    tooltip="Actualizar ahora",
                    on_click=recargar,
                ),
                ft.Dropdown(
                    value=self.id_doctor or "todos",
                    options=opciones,
                    on_select=self._filtrar_doctor,
                    width=230,
                    text_size=13,
                    border=tema.borde_campo(),
                    bgcolor=tema.TARJETA,
                    dense=True,
                ),
                tema.boton_primario("Nueva cita", self._dialogo_nueva_cita, icon=ft.Icons.ADD),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- dashboard (UI-03, UI-05) ----------
    def _vista_dashboard(self) -> ft.Control:
        hoy: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for doctor in self._doctores_visibles():
            dia = self._hoy(doctor)
            hoy += [
                (c, doctor)
                for c in self.citas
                if c["id_doctor"] == doctor["id"]
                and comp.en_zona(c["fecha_hora_inicio"], doctor["zona_horaria"]).date() == dia
            ]
        hoy.sort(key=lambda par: par[0]["fecha_hora_inicio"])
        id_sel = self.cita_sel["id"] if self.cita_sel else None

        async def abrir(cita: dict[str, Any]) -> None:
            await self._abrir_cita(cita)

        tarjetas: list[ft.Control] = [
            comp.tarjeta_cita(c, d, lambda x: self.page.run_task(abrir, x), c["id"] == id_sel)
            for c, d in hoy
        ]
        if not tarjetas:
            tarjetas = [_vacio(ft.Icons.EVENT_AVAILABLE_OUTLINED, "No hay citas para hoy.")]
        pendientes = [a for a in self.alertas if a["estado"] != "resuelta"]
        pendientes = [a for a in pendientes if self.id_doctor in (None, a["id_doctor"])]

        async def ver_alertas(_: Any) -> None:
            await self._ir("alertas")

        resumen_alertas: list[ft.Control] = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                tema.texto(a["nombre_doctor"], 13, ft.FontWeight.W_600),
                                ft.Container(expand=True),
                                tema.badge(*tema.ESTADOS_ALERTA[a["estado"]]),
                            ]
                        ),
                        tema.texto(
                            f"“{a['instruccion_original']}”",
                            13,
                            color=tema.TEXTO_SUAVE,
                            max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=ft.Padding.symmetric(vertical=10),
                border=ft.Border.only(top=ft.BorderSide(1, tema.BORDE)),
            )
            for a in pendientes[:4]
        ] or [tema.texto("Sin alertas por atender.", 13, color=tema.TEXTO_SUAVE)]

        return ft.Column(
            [
                ft.Row(
                    [
                        comp.kpi(
                            "Citas de hoy",
                            self.kpis.get("citas_de_hoy", 0),
                            ft.Icons.CALENDAR_MONTH_OUTLINED,
                            tema.PRIMARIO,
                        ),
                        comp.kpi(
                            "En espera",
                            self.kpis.get("en_espera", 0),
                            ft.Icons.HOURGLASS_EMPTY,
                            tema.AVISO,
                        ),
                        comp.kpi(
                            "Atendidos",
                            self.kpis.get("atendidos", 0),
                            ft.Icons.CHECK_CIRCLE_OUTLINE,
                            "#15803D",
                        ),
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Column(
                            [
                                tema.etiqueta(f"Pacientes de hoy · {len(hoy)}"),
                                ft.ListView(tarjetas, spacing=8, expand=True),
                            ],
                            spacing=10,
                            expand=3,
                        ),
                        ft.Column(
                            [
                                tema.etiqueta("Alertas IA"),
                                tema.tarjeta(
                                    ft.Column(
                                        [
                                            ft.Row(
                                                [
                                                    ft.Icon(
                                                        ft.Icons.SMART_TOY_OUTLINED,
                                                        color=tema.ACENTO,
                                                        size=18,
                                                    ),
                                                    tema.texto(
                                                        f"{len(pendientes)} por atender",
                                                        14,
                                                        ft.FontWeight.W_600,
                                                    ),
                                                    ft.Container(expand=True),
                                                    ft.TextButton(
                                                        "Ver bandeja", on_click=ver_alertas
                                                    ),
                                                ],
                                                spacing=8,
                                            ),
                                            *resumen_alertas,
                                        ],
                                        spacing=8,
                                        tight=True,
                                    ),
                                    relleno=16,
                                ),
                            ],
                            spacing=10,
                            expand=2,
                        ),
                    ],
                    spacing=20,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=20,
            expand=True,
        )

    # ---------- agenda (UI-07, UI-08) ----------
    def _vista_agenda(self) -> ft.Control:
        async def anterior(_: Any) -> None:
            await self._mover_dia(-1)

        async def siguiente(_: Any) -> None:
            await self._mover_dia(1)

        async def hoy(_: Any) -> None:
            await self._mover_dia(None)

        async def abrir(cita: dict[str, Any]) -> None:
            await self._abrir_cita(cita)

        doctores = self._doctores_visibles()
        controles = ft.Row(
            [
                ft.IconButton(ft.Icons.CHEVRON_LEFT, on_click=anterior, tooltip="Día anterior"),
                tema.boton_secundario("Hoy", hoy),
                ft.IconButton(ft.Icons.CHEVRON_RIGHT, on_click=siguiente, tooltip="Día siguiente"),
                ft.Container(expand=True),
                tema.texto("Intervalo", 13, color=tema.TEXTO_SUAVE),
                ft.SegmentedButton(
                    segments=[
                        ft.Segment(value="15", label=ft.Text("15 min")),
                        ft.Segment(value="30", label=ft.Text("30 min")),
                    ],
                    selected=[str(self.intervalo)],
                    show_selected_icon=False,
                    on_change=self._cambiar_intervalo,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if not doctores:
            return ft.Column(
                [controles, _vacio(ft.Icons.PERSON_OUTLINE, "No hay doctores para mostrar.")],
                spacing=14,
                expand=True,
            )
        return ft.Column(
            [
                controles,
                comp.calendario(
                    doctores,
                    self.citas,
                    self.dia,
                    self.intervalo,
                    lambda c: self.page.run_task(abrir, c),
                    self.cita_sel["id"] if self.cita_sel else None,
                ),
            ],
            spacing=14,
            expand=True,
        )

    # ---------- bandeja de alertas (UI-04) ----------
    def _vista_alertas(self) -> ft.Control:
        async def tomar(alerta: dict[str, Any]) -> None:
            await self._tomar(alerta)

        async def resolver(alerta: dict[str, Any]) -> None:
            await self._resolver(alerta)

        visibles = [a for a in self.alertas if self.id_doctor in (None, a["id_doctor"])]
        orden = {"pendiente": 0, "en_proceso": 1, "resuelta": 2}
        visibles.sort(key=lambda a: orden[a["estado"]])
        if not visibles:
            return _vacio(ft.Icons.INBOX_OUTLINED, "La bandeja está vacía.")
        tarjetas = []
        for alerta in visibles:
            doctor = self._doctor(alerta["id_doctor"])
            zona = doctor["zona_horaria"] if doctor else "UTC"
            tarjetas.append(
                comp.tarjeta_alerta(
                    alerta,
                    zona,
                    lambda a: self.page.run_task(tomar, a),
                    lambda a: self.page.run_task(resolver, a),
                )
            )
        return ft.ListView(tarjetas, spacing=12, expand=True)

    # ---------- panel lateral de contexto (UI-06) ----------
    def _panel_contexto(self) -> ft.Container:
        cita = self.cita_sel
        assert cita is not None
        doctor = self._doctor(cita["id_doctor"]) or {"nombre": "", "zona_horaria": "UTC"}
        zona = doctor["zona_horaria"]
        paciente = self.paciente_sel
        nombre = cita["paciente"]["nombre_completo"]
        dia = comp.en_zona(cita["fecha_hora_inicio"], zona).date()

        def dato(icono: str, valor: str | None) -> ft.Row:
            return ft.Row(
                [
                    ft.Icon(icono, size=16, color=tema.TEXTO_SUAVE),
                    tema.texto(
                        valor or "Sin registrar",
                        13,
                        color=tema.TEXTO if valor else tema.TEXTO_TENUE,
                        selectable=True,
                    ),
                ],
                spacing=10,
            )

        def bloque_texto(valor: str | None, vacio: str) -> ft.Container:
            return ft.Container(
                tema.texto(
                    valor or vacio,
                    13,
                    color=tema.TEXTO if valor else tema.TEXTO_TENUE,
                    selectable=True,
                ),
                padding=12,
                bgcolor=tema.FONDO,
                border_radius=8,
                border=ft.Border.all(1, tema.BORDE),
            )

        def accion(estado: str, rotulo: str) -> ft.Control:
            async def aplicar(_: Any) -> None:
                await self._cambiar_estado(estado)

            color = tema.PELIGRO if estado in ("cancelada", "no_asistio") else tema.PRIMARIO
            return ft.Row([tema.boton_secundario(rotulo, aplicar, color=color, expand=True)])

        acciones = [accion(e, r) for e, r in _TRANSICIONES if e != cita["estado"]]
        cerrada = cita["estado"] in ("atendida", "cancelada", "no_asistio")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            tema.etiqueta("Contexto de la cita"),
                            ft.Container(expand=True),
                            ft.IconButton(
                                ft.Icons.CLOSE,
                                icon_size=18,
                                icon_color=tema.TEXTO_SUAVE,
                                tooltip="Cerrar panel",
                                on_click=self._cerrar_panel,
                            ),
                        ]
                    ),
                    ft.Row(
                        [
                            ft.Container(
                                tema.texto(
                                    comp.iniciales(nombre), 16, ft.FontWeight.W_600, tema.PRIMARIO
                                ),
                                width=48,
                                height=48,
                                bgcolor=ft.Colors.with_opacity(0.08, tema.PRIMARIO),
                                border_radius=24,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column(
                                [tema.titulo(nombre, 17), tema.badge_estado(cita["estado"])],
                                spacing=6,
                                expand=True,
                                tight=True,
                            ),
                        ],
                        spacing=14,
                    ),
                    ft.Divider(height=1, color=tema.BORDE),
                    tema.etiqueta("Cita"),
                    dato(ft.Icons.SCHEDULE, f"{comp.fecha_larga(dia)} · {comp.rango(cita, zona)}"),
                    dato(ft.Icons.MEDICAL_SERVICES_OUTLINED, doctor["nombre"]),
                    dato(
                        ft.Icons.SMART_TOY_OUTLINED
                        if cita["origen"] == "ia"
                        else ft.Icons.PERSON_OUTLINE,
                        "Agendada por la IA"
                        if cita["origen"] == "ia"
                        else "Agendada por recepción",
                    ),
                    tema.etiqueta("Motivo de consulta"),
                    bloque_texto(cita["motivo_consulta"], "Sin motivo registrado."),
                    tema.etiqueta("Paciente"),
                    dato(ft.Icons.PHONE_OUTLINED, paciente and paciente["telefono"]),
                    dato(ft.Icons.MAIL_OUTLINE, paciente and paciente["correo"]),
                    tema.etiqueta("Notas clínicas breves"),
                    bloque_texto(
                        paciente and paciente["notas_clinicas_breves"],
                        "Sin notas." if paciente else "Cargando…",
                    ),
                    ft.Divider(height=1, color=tema.BORDE),
                    tema.etiqueta("Cambiar estado"),
                    *(acciones if not cerrada else acciones[:0]),
                    tema.texto(
                        "Esta cita ya está cerrada.", 13, color=tema.TEXTO_SUAVE, visible=cerrada
                    ),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            width=ANCHO_PANEL,
            padding=ft.Padding.only(left=20, right=20, top=16, bottom=16),
            bgcolor=tema.TARJETA,
            border=ft.Border.only(left=ft.BorderSide(1, tema.BORDE)),
            shadow=ft.BoxShadow(
                blur_radius=24,
                color=ft.Colors.with_opacity(0.06, tema.TEXTO),
                offset=ft.Offset(-4, 0),
            ),
        )


def _marca(grande: bool = False) -> ft.Row:
    """Identidad de la clinica: emblema + nombre."""
    lado = 40 if grande else 34
    return ft.Row(
        [
            ft.Container(
                ft.Icon(ft.Icons.LOCAL_HOSPITAL_OUTLINED, color="#FFFFFF", size=lado * 0.55),
                width=lado,
                height=lado,
                bgcolor=tema.PRIMARIO,
                border_radius=10,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Column(
                [
                    tema.texto("Clínica CREE", 18 if grande else 16, ft.FontWeight.W_700),
                    tema.texto("Agenda médica", 11, color=tema.TEXTO_SUAVE),
                ],
                spacing=0,
                tight=True,
            ),
        ],
        spacing=10,
        tight=True,
    )


def _vacio(icono: str, mensaje: str) -> ft.Container:
    return tema.tarjeta(
        ft.Column(
            [
                ft.Icon(icono, size=30, color=tema.TEXTO_TENUE),
                tema.texto(mensaje, 14, color=tema.TEXTO_SUAVE),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            tight=True,
        ),
        relleno=36,
        alignment=ft.Alignment.CENTER,
    )


def main(page: ft.Page) -> None:
    AppRecepcion(page).iniciar()


if __name__ == "__main__":
    if os.environ.get("UI_MODO", "web") == "escritorio":
        ft.run(main)
    else:
        ft.run(
            main,
            view=ft.AppView.WEB_BROWSER,
            host=os.environ.get("UI_HOST", "0.0.0.0"),
            port=int(os.environ.get("UI_PUERTO", "8550")),
            no_cdn=True,  # todo se sirve localmente: la UI no depende de CDNs externos
        )
