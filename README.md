# Agenda Médica Inteligente · Clínica CREE

Microservicio de agenda médica (HIS). Los doctores dictan instrucciones por WhatsApp (texto o
nota de voz), Gemini las interpreta con Function Calling y recepción resuelve lo que la IA no
puede o no debe ejecutar sola. Especificación completa: [`docs/SPEC.md`](docs/SPEC.md).

## Puesta en marcha

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
