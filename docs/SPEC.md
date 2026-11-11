# SPEC — Agenda Médica Inteligente · Clínica CREE

> Fuente de verdad del proyecto. Cada requisito tiene un ID estable. Al modificar un requisito,
> conserva su ID y agrega una línea en el **Registro de cambios** (§7).
> Los puntos marcados **[DEFAULT]** son decisiones por defecto que el usuario puede cambiar.

---

## 1. Arquitectura

### 1.1 Stack
| Capa | Tecnología |
|---|---|
| API y webhooks | Python 3.11+, FastAPI, Uvicorn |
| BD | PostgreSQL 16 (+ extensión `btree_gist`) |
| ORM / validación | SQLAlchemy 2.0 async (asyncpg), Alembic, Pydantic v2 |
| Cifrado | `cryptography` (`MultiFernet`, permite rotar llaves) |
| Tareas / colas | Celery + Redis (broker) + Celery Beat (cron) |
| Caché / contexto IA | Redis (historial de chat con TTL, rate limiting, idempotencia) |
| UI recepción | Flet (desktop y web) |
| IA | Gemini API vía SDK `google-genai`, modelo configurable por `GEMINI_MODEL` |
| Integraciones | WhatsApp Cloud API, Google Calendar API |

> **Nota sobre el modelo:** Gemini 1.5 Flash ya fue retirado. Usar un modelo Flash vigente con
> soporte de audio y function calling, definido en `GEMINI_MODEL` (nunca hardcodeado).

### 1.2 Servicios (contenedores)
- `ARQ-01` **api_core** — CRUD, autenticación de recepción, endpoints que consume la UI.
- `ARQ-02` **api_webhooks** — Recibe WhatsApp. Valida firma, deduplica, encola y responde 200. Sin lógica de negocio.
- `ARQ-03` **worker** — Celery: IA, descarga de audio, Google Calendar, envío de WhatsApp.
- `ARQ-04` **beat** — Celery Beat: cierre nocturno y recordatorios.
- `ARQ-05` **ui** — Flet, consume `api_core` por HTTP con token.
- `ARQ-06` **proxy** — Traefik con TLS (HTTPS obligatorio para Meta y Google). Rutas: `/api` → api_core,
  `/webhooks` → api_webhooks, resto → ui. Solo se levanta con el perfil `produccion` de Compose.

### 1.2b Instalación local para Windows (todo en una PC)
- `ARQ-08` **Modo local** (`MODO_LOCAL=true`): alternativa a Docker para una sola PC con Windows. Un único
  proceso sirve `api_core` (127.0.0.1:8765) y `api_webhooks` (127.0.0.1:8766), ejecuta las tareas en
  segundo plano dentro del mismo proceso (sin Celery) y un planificador propio (sin Beat). Redis se
  sustituye por un almacén clave-valor cifrado sobre PostgreSQL (`almacen_clave_valor`): es un caché
  técnico con caducidad y es la única tabla donde se borran filas físicamente.
- `ARQ-09` **PostgreSQL embebido** (versión 16 o superior): el instalador trae los binarios; el servidor local inicializa y
  arranca la base en `%LOCALAPPDATA%\CREE Agenda\pgdata` (puerto 54329, solo localhost) y aplica las
  migraciones al iniciar.
- `ARQ-10` **Túnel**: con un token de Cloudflare Tunnel configurado, el servidor local abre el túnel que
  da al webhook la dirección https pública que exige Meta. Solo debe publicarse el puerto del webhook.
- `ARQ-11` **App de escritorio**: `CreeAgenda.exe` abre la UI Flet como ventana nativa y arranca el servidor
  local si no está en marcha; `--servidor` corre solo los servicios y `--detener` los apaga. La UI sigue
  hablando con `api_core` por HTTP (nunca con la BD).
- En modo local no aplican `ARQ-02..04` ni `ARQ-06` como contenedores; la lógica de negocio es la misma.

### 1.3 Estructura de carpetas
```
app/
  core/          # config (pydantic-settings), seguridad, cifrado, logging
  db/            # base, sesión async, tipos cifrados
  modelos/       # SQLAlchemy
  esquemas/      # Pydantic
  repositorios/  # acceso a datos
  servicios/     # lógica de negocio (agenda, pacientes, alertas)
  integraciones/ # gemini/, whatsapp/, google_calendar/
  api_core/      # routers
  api_webhooks/  # routers
  worker/        # tareas Celery
ui/              # Flet
escritorio/      # modo local: lanzador, servidor único, PostgreSQL embebido, túnel
instalador/      # empaquetado de Windows (PyInstaller + Inno Setup)
migrations/      # Alembic
tests/
docs/SPEC.md
```

### 1.4 Async y Celery
- `ARQ-07` Celery es síncrono. Las tareas usan un helper `run_async()` que crea su propio event loop
  y su propio engine/sesión por tarea. **Nunca** compartir la sesión de FastAPI con Celery.

---

## 2. Modelo de datos

Todas las tablas incluyen `id` (UUID), `creado_en`, `actualizado_en`, `eliminado_en` (nullable).

- `DAT-01` **Doctor**: `nombre`, `telefono_whatsapp` (E.164, único), `zona_horaria` (IANA, ej. `America/Mexico_City`),
  `hora_cierre_diario` (TIME local), `duracion_cita_default_min` [DEFAULT 30], `credenciales_google_calendar` (cifrado), `activo`.
- `DAT-02` **Paciente**: `nombre_completo`, `telefono`, `correo`, `notas_clinicas_breves` (cifrado).
  `nombre_normalizado` (minúsculas, sin acentos, en claro) para búsqueda.
- `DAT-03` **Cita**: `id_doctor`, `id_paciente`, `fecha_hora_inicio`, `fecha_hora_fin` (TIMESTAMPTZ),
  `motivo_consulta` (cifrado), `estado`, `estado_seguimiento`, `origen` (`ia` | `recepcion`),
  `id_evento_google`, `estado_sync_google` (`pendiente` | `sincronizado` | `error`).
- `DAT-04` **Enums**:
  - `estado`: `programada`, `confirmada`, `en_espera`, `en_consulta`, `atendida`, `cancelada`, `no_asistio`.
  - `estado_seguimiento` [DEFAULT]: `ninguno`, `requiere_seguimiento`, `seguimiento_agendado`.
- `DAT-05` **Antisolapamiento**: constraint de exclusión en PostgreSQL:
  `EXCLUDE USING gist (id_doctor WITH =, tstzrange(fecha_hora_inicio, fecha_hora_fin) WITH &&) WHERE (estado <> 'cancelada' AND eliminado_en IS NULL)`.
  La aplicación captura la violación y devuelve "horario ocupado" con alternativas. (`SELECT FOR UPDATE`
  no basta porque no bloquea filas que aún no existen.)
- `DAT-06` **Recordatorio**: `id_doctor`, `fecha_hora`, `descripcion` (cifrado), `estado` (`pendiente` | `enviado` | `cancelado`).
- `DAT-07` **AlertaRecepcion**: `id_doctor`, `mensaje_ia` (cifrado), `instruccion_original` (cifrado), `estado` (`pendiente` | `en_proceso` | `resuelta`),
  `resuelta_por`, `resuelta_en`.
- `DAT-08` **UsuarioRecepcion**: `nombre`, `correo`, `hash_password`, `rol` (`recepcion` | `admin`), `doctores_asignados`
  (arreglo de IDs de doctor; `recepcion` solo ve esos doctores, `admin` ve todos y gestiona doctores y usuarios).
- `DAT-09` **LogAuditoria**: `entidad`, `id_entidad`, `accion`, `actor` (`usuario:<id>` | `ia:<doctor_id>` | `sistema`),
  `cambios` (JSON **sin** campos cifrados en claro), `fecha`. Append-only.

---

## 3. Flujos de IA y WhatsApp

### 3.1 Webhook
- `WA-01` Verificación `GET` con `hub.verify_token`.
- `WA-02` Validar firma `X-Hub-Signature-256` con el App Secret. Firma inválida → 401.
- `WA-03` Idempotencia: Meta reintenta. Guardar `message.id` en Redis (`SET NX`, TTL 48 h); si existe, ignorar.
- `WA-04` Solo se aceptan mensajes de números registrados como Doctor. Otros → se ignoran y se registran.
- `WA-05` Tipos soportados: `text` y `audio`. Otros → respuesta cortés "solo texto o nota de voz".
- `WA-06` Encolar en Celery y responder 200 de inmediato. Si la cola no está disponible se responde 503
  y se libera la marca de idempotencia, para que el reintento de Meta no pierda el mensaje.

### 3.2 Pipeline de audio
- `IA-01` Worker: `GET /{media_id}` con Bearer Token → URL; `GET` a la URL → archivo `.ogg`.
- `IA-02` El audio se envía a Gemini en memoria (bytes inline). **No se persiste en disco ni en BD.**
- `IA-03` Límite de tamaño/duración configurable [DEFAULT 2 min, 5 MB]; si excede, pedir que lo divida.
  La duración se lee de la cabecera OGG, sin decodificar el audio.

### 3.3 Contexto
- `IA-04` Historial por doctor en Redis: clave `chat:{doctor_id}`, últimos N turnos [DEFAULT 10], TTL [DEFAULT 2 h].
- `IA-05` System prompt incluye: fecha y hora actual **en la zona del doctor**, duración default, y reglas:
  convertir horas relativas ("mañana a las 5") a ISO 8601 con offset; nunca inventar pacientes; ante duda, aclarar.

### 3.4 Tools (Function Calling)
| ID | Tool | Comportamiento |
|---|---|---|
| `IA-06` | `buscar_paciente(nombre)` | Busca por `nombre_normalizado`. Devuelve 0, 1 o varias coincidencias. |
| `IA-07` | `consultar_disponibilidad(fecha, duracion_minutos)` | Devuelve huecos libres del doctor dentro de la jornada [DEFAULT 08:00–20:00 en su zona]. |
| `IA-08` | `agendar_cita(id_paciente \| nombre_paciente_nuevo, fecha_hora_iso, duracion_minutos, motivo)` | Crea cita. Si el paciente es nuevo, lo crea. Si choca (`DAT-05`), devuelve alternativas. |
| `IA-09` | `crear_recordatorio_tarea(fecha_hora_iso, descripcion_tarea)` | Crea `Recordatorio`. |
| `IA-10` | `delegar_a_recepcion(instruccion_literal)` | Crea `AlertaRecepcion`. |
| `IA-11` | `solicitar_aclaracion(pregunta)` | Responde al doctor por WhatsApp y espera. |

- `IA-12` **Human-in-the-loop** [DEFAULT]: la IA puede agendar directamente si hay coincidencia única de
  paciente y el horario está libre. Se **delega a recepción** si: varias coincidencias de paciente sin
  resolver, cancelaciones/reprogramaciones, o cualquier acción que implique contactar al paciente.
- `IA-13` Toda acción de la IA responde al doctor con confirmación en texto (ej. "Agendé a Ana López mañana 17:00–17:30").
- `IA-14` Límite de iteraciones de function calling por mensaje [DEFAULT 5]. Si se alcanza sin terminar,
  la instrucción se delega a recepción y se avisa al doctor.

### 3.5 Cierre nocturno y recordatorios
- `IA-15` Beat revisa cada 15 min qué doctores llegaron a su `hora_cierre_diario` local y encola el resumen.
- `IA-16` El resumen se envía con **plantilla aprobada por Meta** (fuera de la ventana de 24 h solo se permiten plantillas).
- `IA-17` Se guarda en Redis que se hizo la pregunta de cierre, para interpretar la respuesta del doctor en contexto.
- `IA-18` Recordatorios (`DAT-06`) se envían a su hora; si la ventana de 24 h está cerrada, usar plantilla.
  La ventana se registra en Redis (`wa_ventana:{doctor_id}`, TTL 24 h) con cada mensaje entrante del doctor.
- `IA-19` Plantillas de Meta: `cierre_diario` (doctor, atendidas, sin cerrar, citas de mañana) y
  `recordatorio_tarea` (descripción). Nombres e idioma configurables por entorno.

### 3.6 Google Calendar
- `GC-01` Al crear/modificar/cancelar una cita, el worker sincroniza el evento (sin datos clínicos en el evento: solo "Consulta" + nombre del paciente [DEFAULT]).
- `GC-02` Reintentos con backoff; tras agotar, `estado_sync_google = error` y alerta a recepción.
- `GC-03` OAuth2 por doctor; tokens cifrados (`DAT-01`) y refresco automático.

---

## 4. UI de recepción (Flet)

Estilo: Hospital Information System, minimalista, premium. Cero estética comercial.

- `UI-01` Paleta: fondo `#F8FAFC`, tarjetas `#FFFFFF`, primario `#0369A1` (acento secundario `#0F766E`), texto `#1E293B`.
- `UI-02` Login de recepción contra `api_core` (`DAT-08`).
- `UI-03` Dashboard: KPIs `Citas de hoy`, `En espera`, `Atendidos`; filtro por doctor.
- `UI-04` Bandeja de alertas IA (`DAT-07`): tarjetas con instrucción original, botones "Tomar" y "Resolver".
- `UI-05` Tarjetas de paciente en distribución horizontal con badge de estado translúcido.
- `UI-06` Panel lateral de contexto: al hacer clic en una cita, muestra datos y notas del paciente sin salir de la vista.
- `UI-07` Calendario time-blocking por columnas (una por doctor), intervalos de 15/30 min seleccionables.
- `UI-08` Las horas se muestran en la zona del doctor de cada columna.
- `UI-09` Refresco: polling cada 30 s [DEFAULT] (WebSocket en una fase posterior si se pide).
- `UI-10` Desde el panel lateral (`UI-06`) recepción cambia el estado de la cita (confirmar, en espera,
  en consulta, atendida, no asistió, cancelar).
- `UI-12` **Ajustes** (solo rol admin): Integraciones (Gemini, WhatsApp, conexión pública, Google Calendar),
  Doctores (alta, edición y conexión de Google Calendar) y Usuarios (alta). Los secretos son de solo
  escritura: la API nunca los devuelve, solo indica si están configurados. Editables únicamente en modo
  local (`PUT /api/ajustes`); con Docker se muestran en solo lectura porque se definen en `.env`.
- `UI-13` **Instalación inicial** (modo local): mientras no exista ningún usuario, la app pide crear la cuenta
  de administración (`POST /api/instalacion/admin`). Después ese endpoint queda cerrado.
- `UI-11` Diálogo "Nueva cita": doctor, paciente (existente por nombre o nuevo), fecha y hora en la zona
  del doctor, duración y motivo. Si el horario está ocupado muestra las alternativas.

---

## 5. Seguridad, cumplimiento y despliegue

- `SEG-01` Cifrado de campos médicos con un `TypeDecorator` de SQLAlchemy usando `MultiFernet`
  (llaves en `FERNET_KEYS`, la primera cifra, todas descifran). Los campos cifrados **no son buscables**.
- `SEG-02` Logs sin PHI: filtro de logging que redacta campos sensibles y contenido de mensajes.
- `SEG-03` Autenticación JWT para `api_core` (passwords con scrypt); los webhooks se protegen solo con firma
  de Meta. Con `ENTORNO=produccion` el servicio no arranca sin `FERNET_KEYS` o con `JWT_SECRET` de menos de 32 caracteres.
- `SEG-04` Rate limiting por doctor en Redis [DEFAULT 20 mensajes por minuto]. El proxy limita además las
  peticiones por IP hacia `api_core`.
- `SEG-05` Referencia normativa: NOM-024-SSA3 y LFPDPPP (México); HIPAA como guía. Este sistema no
  sustituye una revisión legal formal.
- `DEP-01` Docker Compose con todos los servicios de `ARQ-*`, healthchecks y volúmenes para Postgres.
- `DEP-02` Proxy inverso con TLS (Let's Encrypt).
- `DEP-04` **Instalador de Windows**: `instalador/construir.ps1` genera `CREE-Agenda-Instalador-<versión>.exe`
  (PyInstaller + Inno Setup) con la app, PostgreSQL y el cliente del túnel. Instala por usuario, sin
  permisos de administrador, y puede iniciar los servicios al encender la PC. La configuración se genera
  sola en el primer arranque (`config.env` con llaves de cifrado, sesión y base de datos). Los datos de
  `%LOCALAPPDATA%\CREE Agenda` no se borran al actualizar ni al desinstalar. Un workflow de GitHub Actions
  lo construye en Windows y corre una prueba de humo del ejecutable.
- `SEG-06` En modo local la configuración y la llave de cifrado viven en `config.env`, dentro del perfil del
  usuario de Windows. Debe respaldarse: sin `FERNET_KEYS` los datos médicos no se pueden leer.
- `DEP-03` `.env.example` con: `DATABASE_URL`, `REDIS_URL`, `FERNET_KEYS`, `JWT_SECRET`, `GEMINI_API_KEY`,
  `GEMINI_MODEL`, `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`, `WA_APP_SECRET`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. Además: `ENTORNO`, `POSTGRES_PASSWORD`,
  `WA_API_VERSION`, `WA_PLANTILLA_CIERRE`, `WA_PLANTILLA_RECORDATORIO`, `WA_PLANTILLA_IDIOMA`, `DOMINIO`,
  `ACME_EMAIL`, `API_CORE_URL`.

---

## 6. Plan por fases

Cada fase termina con tests pasando y `docker compose up` funcionando. No avanzar sin orden del usuario.

| Fase | Contenido | IDs |
|---|---|---|
| 1 | Esqueleto, Docker Compose, config, BD, modelos, migraciones, cifrado, auditoría | ARQ-01..07, DAT-*, SEG-01/02, DEP-01/03 |
| 2 | `api_core`: auth y CRUD de doctores, pacientes, citas, alertas | SEG-03, DAT-05 |
| 3 | Webhook de WhatsApp (texto) + Celery + Gemini con tools | WA-*, IA-04..14 |
| 4 | Pipeline de audio | IA-01..03 |
| 5 | Cierre nocturno, recordatorios, plantillas | IA-15..18 |
| 6 | Google Calendar | GC-* |
| 7 | UI Flet | UI-* |
| 8 | Proxy, TLS, hardening, rate limiting | DEP-02, SEG-04 |
| 9 | App de escritorio e instalador de Windows (modo local), Ajustes | ARQ-08..11, UI-12/13, DEP-04, SEG-06 |

---

## 7. Registro de cambios
| Fecha | ID | Cambio |
|---|---|---|
| 2026-11-10 | — | Versión inicial reestructurada. |
| 2026-11-10 | ARQ-06 | Se eligió Traefik; rutas `/api`, `/webhooks` y UI; perfil `produccion`. |
| 2026-11-10 | DAT-06, DAT-07 | Textos libres del doctor (`descripcion`, `mensaje_ia`, `instruccion_original`) van cifrados. |
| 2026-11-10 | DAT-08 | `doctores_asignados` como arreglo de IDs; permisos por rol. |
| 2026-11-10 | WA-06 | Respuesta 503 si no se puede encolar. |
| 2026-11-10 | IA-03, IA-07, IA-14, IA-18 | Defaults concretos: límite de audio, jornada, delegación al agotar pasos, ventana de 24 h en Redis. |
| 2026-11-10 | IA-19 | Nuevo: definición de las plantillas de Meta. |
| 2026-11-10 | UI-10, UI-11 | Nuevos: cambio de estado desde el panel y diálogo "Nueva cita". |
| 2026-11-10 | SEG-03, SEG-04 | scrypt, validación de secretos en producción, default de rate limiting. |
| 2026-11-10 | DEP-03 | Variables de entorno adicionales. |
| 2026-11-11 | ARQ-08..11, DEP-04, SEG-06 | Nuevo: instalación local para Windows sin Docker (sin Redis ni Celery), PostgreSQL embebido, túnel e instalador. |
| 2026-11-11 | UI-12, UI-13 | Nuevos: vista de Ajustes e instalación inicial; endpoints `/api/ajustes` e `/api/instalacion/*`. |
