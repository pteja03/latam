# Agenda Médica Inteligente · Clínica CREE

Microservicio de agenda médica (HIS). Los doctores dictan instrucciones por WhatsApp (texto o
nota de voz), Gemini las interpreta con Function Calling y recepción resuelve lo que la IA no
puede o no debe ejecutar sola. Especificación completa: [`docs/SPEC.md`](docs/SPEC.md).

## App de escritorio para Windows (todo en una PC)

Instalación sin Docker: un instalador deja en la PC la app de recepción, la base de datos y los
servicios de IA y WhatsApp.

1. Descarga `CREE-Agenda-Instalador-<versión>.exe` desde la pestaña **Actions** del repositorio
   (workflow "Instalador de Windows" → artefacto `CREE-Agenda-Instalador`) y ejecútalo.
2. Al abrir la app por primera vez, crea la cuenta de administración.
3. En **Ajustes** configura Gemini, WhatsApp, la conexión pública y, si quieres, Google Calendar;
   registra a los doctores y da de alta al personal de recepción.

A tener en cuenta:

- La PC debe permanecer encendida y con la sesión iniciada para que los doctores reciban respuesta.
- WhatsApp exige una dirección https pública. La forma prevista es un túnel de Cloudflare que apunte a
  `http://localhost:8766`; pega su token en Ajustes → Conexión pública.
- Los datos viven en `%LOCALAPPDATA%\CREE Agenda` y no se borran al actualizar ni al desinstalar.
  **Respalda esa carpeta**: `config.env` contiene la llave que cifra los datos médicos.

Para construir el instalador en una PC con Windows: `pip install ".[escritorio]"`, instalar Inno Setup 6
y correr `powershell -ExecutionPolicy Bypass -File instalador\construir.ps1`.

## Puesta en marcha con Docker (servidor)

```bash
cp .env.example .env            # completar llaves (ver comentarios del archivo)
docker compose up -d            # postgres, redis, migraciones, api_core, api_webhooks, worker, beat, ui
docker compose exec api_core python -m app.cli crear-admin --nombre "Admin" --correo admin@cree.mx
```

| Servicio | Desarrollo | Producción (detrás del proxy) |
|---|---|---|
| UI de recepción | http://localhost:8550 | `https://DOMINIO/` |
| api_core (docs en `/api/docs`) | http://localhost:8000 | `https://DOMINIO/api` |
| Webhook de WhatsApp | http://localhost:8001/webhooks/whatsapp | `https://DOMINIO/webhooks/whatsapp` |

Producción (TLS con Let's Encrypt, solo se publican 80/443):

```bash
docker compose --profile produccion up -d     # requiere ENTORNO=produccion, DOMINIO y ACME_EMAIL
```

Datos ficticios para revisar la interfaz (solo desarrollo):

```bash
docker compose exec api_core python -m app.cli datos-demo
```

## Configuración externa pendiente

- **Meta**: registrar el webhook `https://DOMINIO/webhooks/whatsapp` con `WA_VERIFY_TOKEN` y dar
  de alta dos plantillas aprobadas, con variables de cuerpo en este orden:
  - `cierre_diario`: `{{1}}` doctor, `{{2}}` citas atendidas, `{{3}}` citas sin cerrar, `{{4}}` citas de mañana.
  - `recordatorio_tarea`: `{{1}}` descripción del recordatorio.
- **Google**: crear credenciales OAuth con redirect `https://DOMINIO/api/google/oauth/callback`.
  Cada doctor se conecta desde `GET /api/google/oauth/iniciar?id_doctor=...` (rol admin).
- **Gemini**: `GEMINI_API_KEY` y un modelo Flash vigente en `GEMINI_MODEL`.

## Desarrollo

```bash
pip install -e ".[dev]"
alembic upgrade head
pytest                          # usa PostgreSQL real: TEST_DATABASE_URL (ver tests/conftest.py)
ruff check . && ruff format .
```

Los tests simulan siempre Gemini, Meta y Google.
