"""Vista de Ajustes (UI-12): integraciones, doctores y usuarios. Solo para el rol admin."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import flet as ft

from ui import tema
from ui.api import ClienteApi, ErrorApi

ZONAS = [
    "America/Mexico_City", "America/Monterrey", "America/Cancun", "America/Chihuahua",
    "America/Hermosillo", "America/Mazatlan", "America/Tijuana", "America/Bogota",
    "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires", "America/New_York",
    "Europe/Madrid", "UTC",
]  # fmt: skip
_SECCIONES = [
    ("integraciones", "Integraciones"),
    ("doctores", "Doctores"),
    ("usuarios", "Usuarios"),
]

# (campo, rotulo, ayuda)
_GEMINI = [
    ("gemini_api_key", "API key de Gemini", "Se obtiene en Google AI Studio."),
    ("gemini_model", "Modelo", "Un modelo Flash vigente, por ejemplo gemini-flash-latest."),
]
_WHATSAPP = [
    ("wa_access_token", "Token de acceso", "Token permanente de la app de Meta."),
    ("wa_phone_number_id", "ID del número de teléfono", "Identificador del número en Meta."),
    ("wa_app_secret", "App Secret", "Valida que los mensajes vienen de Meta."),
    ("wa_api_version", "Versión de la API", ""),
    ("wa_plantilla_cierre", "Plantilla de cierre diario", "Nombre aprobado en Meta."),
    ("wa_plantilla_recordatorio", "Plantilla de recordatorio", "Nombre aprobado en Meta."),
    ("wa_plantilla_idioma", "Idioma de las plantillas", "Por ejemplo es_MX."),
]
_PUBLICA = [
    ("url_publica", "Dirección pública (https)", "La que apunta a esta PC, sin ruta."),
    ("tunel_token", "Token de Cloudflare Tunnel", "Opcional: abre el túnel automáticamente."),
]
_GOOGLE = [
    ("google_client_id", "Client ID", "Credencial OAuth de Google Cloud."),
    ("google_client_secret", "Client Secret", ""),
    ("google_redirect_uri", "URI de redirección", "Regístrala tal cual en Google Cloud."),
]


class Anfitrion(Protocol):
    """Lo que la vista necesita de la aplicacion principal."""

    page: ft.Page
    api: ClienteApi
    doctores: list[dict[str, Any]]

    def _aviso(self, mensaje: str, error: bool = False) -> None: ...
    async def _seguro(self, corrutina: Any) -> Any: ...
    async def refrescar(self, forzar: bool = False) -> None: ...
    def _dibujar(self) -> None: ...


class VistaAjustes:
    def __init__(self, app: Anfitrion) -> None:
        self.app = app
        self.seccion = "integraciones"
        self.datos: dict[str, Any] | None = None
        self.usuarios: list[dict[str, Any]] = []
        self._campos: dict[str, ft.TextField] = {}

    async def cargar(self) -> None:
        resultado = await self.app._seguro(self.app.api.ajustes())
        if resultado is not None:
            self.datos = resultado
        usuarios = await self.app._seguro(self.app.api.usuarios())
        if usuarios is not None:
            self.usuarios = usuarios

    # ================= estructura =================
    def construir(self) -> ft.Control:
        async def cambiar(evento: ft.Event[ft.SegmentedButton]) -> None:
            self.seccion = next(iter(evento.control.selected))
            self.app._dibujar()

        selector = ft.SegmentedButton(
            segments=[ft.Segment(value=v, label=ft.Text(r)) for v, r in _SECCIONES],
            selected=[self.seccion],
            show_selected_icon=False,
            on_change=cambiar,
        )
        cuerpo = {
            "integraciones": self._integraciones,
            "doctores": self._doctores,
            "usuarios": self._usuarios,
        }[self.seccion]()
        return ft.Column([ft.Row([selector]), cuerpo], spacing=16, expand=True)

    # ================= integraciones =================
    def _campo(self, campo: str, rotulo: str, ayuda: str) -> ft.TextField:
        assert self.datos is not None
        editable = self.datos["editable"]
        secreto = campo in self.datos["secretos_configurados"]
        if secreto:
            configurado = self.datos["secretos_configurados"][campo]
            control = tema.campo(
                rotulo,
                password=True,
                can_reveal_password=True,
                hint_text="Configurado · escribe para reemplazar"
                if configurado
                else "Sin configurar",
                helper=ayuda or None,
                disabled=not editable,
            )
        else:
            control = tema.campo(
                rotulo,
                value=self.datos["valores"].get(campo, ""),
                helper=ayuda or None,
                disabled=not editable,
            )
        self._campos[campo] = control
        return control

    def _grupo(self, titulo: str, descripcion: str, listo: bool, campos: list, extra=None):
        controles: list[ft.Control] = [
            ft.Row(
                [
                    tema.texto(titulo, 16, ft.FontWeight.W_600),
                    ft.Container(expand=True),
                    tema.badge("Listo", "#15803D")
                    if listo
                    else tema.badge("Falta configurar", tema.AVISO),
                ]
            ),
            tema.texto(descripcion, 13, color=tema.TEXTO_SUAVE),
            *[self._campo(*c) for c in campos],
        ]
        if extra:
            controles += extra
        return tema.tarjeta(
            ft.Column(
                controles,
                spacing=12,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def _dato_copiable(self, rotulo: str, valor: str) -> ft.Control:
        async def copiar(_: Any) -> None:
            await ft.Clipboard().set(valor)
            self.app._aviso(f"{rotulo} copiado")

        return ft.Container(
            ft.Row(
                [
                    ft.Column(
                        [
                            tema.etiqueta(rotulo),
                            tema.texto(
                                valor or "Aún sin definir",
                                13,
                                selectable=True,
                                color=tema.TEXTO if valor else tema.TEXTO_TENUE,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                        tight=True,
                    ),
                    ft.IconButton(
                        ft.Icons.CONTENT_COPY,
                        icon_size=16,
                        icon_color=tema.TEXTO_SUAVE,
                        tooltip="Copiar",
                        on_click=copiar,
                        disabled=not valor,
                    ),
                ]
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=tema.FONDO,
            border=ft.Border.all(1, tema.BORDE),
            border_radius=8,
        )

    def _integraciones(self) -> ft.Control:
        if self.datos is None:
            return tema.tarjeta(tema.texto("Cargando ajustes…", 14, color=tema.TEXTO_SUAVE))
        self._campos = {}
        valores, secretos = self.datos["valores"], self.datos["secretos_configurados"]
        gemini_ok = secretos["gemini_api_key"] and bool(valores["gemini_model"])
        whatsapp_ok = (
            secretos["wa_access_token"]
            and secretos["wa_app_secret"]
            and bool(valores["wa_phone_number_id"])
        )
        publica_ok = bool(valores["url_publica"])
        google_ok = bool(valores["google_client_id"]) and secretos["google_client_secret"]
        aviso: list[ft.Control] = []
        if not self.datos["editable"]:
            aviso = [
                ft.Container(
                    tema.texto(
                        "En este despliegue los ajustes se definen en el archivo .env del "
                        "servidor. Aquí solo se muestran.",
                        13,
                        color=tema.AVISO,
                    ),
                    padding=12,
                    bgcolor=ft.Colors.with_opacity(0.08, tema.AVISO),
                    border_radius=8,
                )
            ]

        async def guardar(_: Any) -> None:
            await self._guardar()

        return ft.ListView(
            [
                *aviso,
                self._grupo(
                    "Asistente de IA (Gemini)",
                    "Interpreta los mensajes de texto y las notas de voz de los doctores.",
                    gemini_ok,
                    _GEMINI,
                ),
                self._grupo(
                    "WhatsApp Cloud API",
                    "Canal por el que los doctores envían instrucciones y reciben respuestas.",
                    whatsapp_ok,
                    _WHATSAPP,
                    [
                        tema.texto(
                            "Datos para registrar el webhook en Meta:", 13, color=tema.TEXTO_SUAVE
                        ),
                        self._dato_copiable("URL del webhook", self.datos["url_webhook"]),
                        self._dato_copiable("Token de verificación", valores["wa_verify_token"]),
                    ],
                ),
                self._grupo(
                    "Conexión pública",
                    "Meta necesita una dirección https pública para entregar los mensajes a esta "
                    "PC. Con un token de Cloudflare Tunnel la conexión se abre sola al iniciar.",
                    publica_ok,
                    _PUBLICA,
                ),
                self._grupo(
                    "Google Calendar",
                    "Opcional. Copia cada cita al calendario del doctor, sin datos clínicos. "
                    "Cada doctor se conecta desde la sección Doctores.",
                    google_ok,
                    _GOOGLE,
                ),
                ft.Row(
                    [
                        ft.Container(expand=True),
                        tema.boton_primario(
                            "Guardar ajustes", guardar, disabled=not self.datos["editable"]
                        ),
                    ]
                ),
            ],
            spacing=14,
            expand=True,
        )

    async def _guardar(self) -> None:
        assert self.datos is not None
        cambios: dict[str, str] = {}
        for campo, control in self._campos.items():
            valor = (control.value or "").strip()
            if campo in self.datos["secretos_configurados"]:
                if valor:  # un secreto vacio significa "no cambiar"
                    cambios[campo] = valor
            elif valor != self.datos["valores"].get(campo, ""):
                cambios[campo] = valor
        if not cambios:
            self.app._aviso("No hay cambios por guardar")
            return
        resultado = await self.app._seguro(self.app.api.guardar_ajustes(cambios))
        if resultado is not None:
            self.datos = resultado
            self.app._aviso("Ajustes guardados")
            self.app._dibujar()

    # ================= doctores =================
    def _doctores(self) -> ft.Control:
        async def nuevo(_: Any) -> None:
            self._dialogo_doctor(None)

        tarjetas: list[ft.Control] = [self._tarjeta_doctor(d) for d in self.app.doctores]
        if not tarjetas:
            tarjetas = [
                tema.tarjeta(
                    tema.texto(
                        "Aún no hay doctores. Registra al primero con su número de WhatsApp.",
                        14,
                        color=tema.TEXTO_SUAVE,
                    )
                )
            ]
        return ft.Column(
            [
                ft.Row(
                    [
                        tema.texto(
                            "Solo los números registrados aquí pueden dar instrucciones por "
                            "WhatsApp.",
                            13,
                            color=tema.TEXTO_SUAVE,
                        ),
                        ft.Container(expand=True),
                        tema.boton_primario("Nuevo doctor", nuevo, icon=ft.Icons.ADD),
                    ]
                ),
                ft.ListView(tarjetas, spacing=10, expand=True),
            ],
            spacing=12,
            expand=True,
        )

    def _tarjeta_doctor(self, doctor: dict[str, Any]) -> ft.Control:
        async def editar(_: Any) -> None:
            self._dialogo_doctor(doctor)

        async def conectar(_: Any) -> None:
            url = await self.app._seguro(self.app.api.url_google(doctor["id"]))
            if url:
                await ft.UrlLauncher().launch_url(url)
                self.app._aviso("Termina la autorización en el navegador y luego actualiza.")

        conectado = doctor["google_calendar_conectado"]
        return tema.tarjeta(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    tema.texto(doctor["nombre"], 15, ft.FontWeight.W_600),
                                    tema.badge("Activo", "#15803D")
                                    if doctor["activo"]
                                    else tema.badge("Inactivo", tema.TEXTO_SUAVE),
                                ],
                                spacing=10,
                            ),
                            tema.texto(
                                f"{doctor['telefono_whatsapp']} · {doctor['zona_horaria']} · "
                                f"cierre {doctor['hora_cierre_diario'][:5]} · "
                                f"citas de {doctor['duracion_cita_default_min']} min",
                                13,
                                color=tema.TEXTO_SUAVE,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                        tight=True,
                    ),
                    tema.badge("Google Calendar conectado", tema.ACENTO)
                    if conectado
                    else tema.boton_secundario("Conectar Google Calendar", conectar),
                    tema.boton_secundario("Editar", editar),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            relleno=16,
        )

    def _dialogo_doctor(self, doctor: dict[str, Any] | None) -> None:
        d = doctor or {}
        nombre = tema.campo("Nombre", value=d.get("nombre", ""), autofocus=True)
        telefono = tema.campo(
            "WhatsApp (formato internacional)",
            value=d.get("telefono_whatsapp", ""),
            hint_text="+5215512345678",
        )
        zona = ft.Dropdown(
            label="Zona horaria",
            value=d.get("zona_horaria", ZONAS[0]),
            options=[ft.DropdownOption(key=z, text=z) for z in ZONAS],
            border=tema.borde_campo(),
            text_size=14,
            expand=True,
        )
        cierre = tema.campo(
            "Hora de cierre",
            value=d.get("hora_cierre_diario", "20:00")[:5],
            hint_text="HH:MM",
            expand=True,
        )
        duracion = tema.campo(
            "Minutos por cita", value=str(d.get("duracion_cita_default_min", 30)), expand=True
        )
        activo = ft.Switch(label="Activo", value=d.get("activo", True))

        async def guardar() -> str | None:
            try:
                minutos = int((duracion.value or "").strip())
            except ValueError:
                return "Los minutos por cita deben ser un número."
            datos = {
                "nombre": (nombre.value or "").strip(),
                "telefono_whatsapp": (telefono.value or "").replace(" ", ""),
                "zona_horaria": zona.value,
                "hora_cierre_diario": (cierre.value or "").strip(),
                "duracion_cita_default_min": minutos,
                "activo": bool(activo.value),
            }
            if doctor is None:
                await self.app.api.crear_doctor(datos)
            else:
                await self.app.api.actualizar_doctor(doctor["id"], datos)
            return None

        self._dialogo(
            "Editar doctor" if doctor else "Nuevo doctor",
            [nombre, telefono, ft.Row([zona]), ft.Row([cierre, duracion], spacing=10), activo],
            guardar,
            "Revisa el nombre, el teléfono (+ y solo dígitos) y la hora (HH:MM).",
        )

    # ================= usuarios =================
    def _usuarios(self) -> ft.Control:
        async def nuevo(_: Any) -> None:
            self._dialogo_usuario()

        nombres = {d["id"]: d["nombre"] for d in self.app.doctores}
        filas: list[ft.Control] = []
        for usuario in self.usuarios:
            if usuario["rol"] == "admin":
                alcance = "Todos los doctores"
            else:
                asignados = [nombres.get(i, "—") for i in usuario["doctores_asignados"]]
                alcance = ", ".join(asignados) or "Sin doctores asignados"
            filas.append(
                tema.tarjeta(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    tema.texto(usuario["nombre"], 15, ft.FontWeight.W_600),
                                    tema.texto(
                                        f"{usuario['correo']} · {alcance}",
                                        13,
                                        color=tema.TEXTO_SUAVE,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                                tight=True,
                            ),
                            tema.badge("Administración", tema.PRIMARIO)
                            if usuario["rol"] == "admin"
                            else tema.badge("Recepción", tema.ACENTO),
                        ]
                    ),
                    relleno=16,
                )
            )
        return ft.Column(
            [
                ft.Row(
                    [
                        tema.texto(
                            "Cuentas del personal que usa esta aplicación.",
                            13,
                            color=tema.TEXTO_SUAVE,
                        ),
                        ft.Container(expand=True),
                        tema.boton_primario("Nuevo usuario", nuevo, icon=ft.Icons.ADD),
                    ]
                ),
                ft.ListView(filas, spacing=10, expand=True),
            ],
            spacing=12,
            expand=True,
        )

    def _dialogo_usuario(self) -> None:
        nombre = tema.campo("Nombre", autofocus=True)
        correo = tema.campo("Correo")
        password = tema.campo(
            "Contraseña (mínimo 8 caracteres)", password=True, can_reveal_password=True
        )
        rol = ft.Dropdown(
            label="Rol",
            value="recepcion",
            options=[
                ft.DropdownOption(key="recepcion", text="Recepción (solo sus doctores)"),
                ft.DropdownOption(key="admin", text="Administración (todo y ajustes)"),
            ],
            border=tema.borde_campo(),
            text_size=14,
            expand=True,
        )
        casillas = [
            ft.Checkbox(label=d["nombre"], value=True, data=d["id"]) for d in self.app.doctores
        ]

        async def guardar() -> str | None:
            await self.app.api.crear_usuario(
                {
                    "nombre": (nombre.value or "").strip(),
                    "correo": (correo.value or "").strip(),
                    "password": password.value or "",
                    "rol": rol.value,
                    "doctores_asignados": [c.data for c in casillas if c.value],
                }
            )
            return None

        self._dialogo(
            "Nuevo usuario",
            [
                nombre,
                correo,
                password,
                ft.Row([rol]),
                tema.etiqueta("Doctores que atiende"),
                *casillas,
            ],
            guardar,
            "Revisa el nombre, el correo y que la contraseña tenga al menos 8 caracteres.",
        )

    # ================= dialogo generico =================
    def _dialogo(
        self,
        titulo: str,
        controles: list[ft.Control],
        guardar: Callable[[], Awaitable[str | None]],
        mensaje_invalido: str,
    ) -> None:
        error = tema.texto("", 13, color=tema.PELIGRO, visible=False)

        async def aceptar(_: Any) -> None:
            try:
                problema = await guardar()
            except ErrorApi as fallo:
                problema = mensaje_invalido if fallo.estado == 422 else fallo.detalle
            if problema:
                error.value, error.visible = problema, True
                self.app.page.update()
                return
            self.app.page.pop_dialog()
            self.app._aviso("Guardado")
            await self.cargar()
            await self.app.refrescar(forzar=True)

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=tema.TARJETA,
                shape=ft.RoundedRectangleBorder(radius=14),
                title=tema.titulo(titulo, 18),
                content=ft.Container(
                    ft.Column(
                        [*controles, error],
                        spacing=14,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    width=460,
                ),
                scrollable=True,
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.app.page.pop_dialog()),
                    tema.boton_primario("Guardar", aceptar),
                ],
            )
        )
