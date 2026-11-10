# Guía de contribución — Agenda Médica Inteligente · Clínica CREE

> Reglas de trabajo del proyecto. Léelas antes de cada cambio.
> La especificación completa está en `docs/SPEC.md`. Cada requisito tiene un ID (ej. `DAT-03`, `IA-05`).
> Cuando el usuario cite un ID, ese es el alcance exacto de la tarea.

## 1. Qué es este proyecto
Microservicio de agenda médica (HIS) para la Clínica CREE. Los doctores dictan instrucciones por
WhatsApp (texto o nota de voz); un modelo Gemini las interpreta con Function Calling; recepción
revisa y resuelve lo que la IA no puede o no debe ejecutar sola (human-in-the-loop).

**No es un CRM.** Prohibido usar términos o patrones de ventas: lead, funnel, pipeline, deal,
cliente, conversión, prospecto. Se dice **paciente, cita, consulta, seguimiento, recepción**.

## 2. Protocolo de trabajo (OBLIGATORIO en cada orden)

### 2.1 Alcance mínimo
1. Haz **solo** lo que se pidió. Nada de refactors, renombres, reformateos ni "mejoras" no solicitadas.
2. No toques archivos fuera del alcance. Si crees que otro archivo debe cambiar, **dilo y pregunta**.
3. No agregues dependencias nuevas sin preguntar primero.
4. No cambies firmas públicas (endpoints, esquemas Pydantic, modelos, tools de Gemini) sin preguntar.
5. Si una orden contradice `docs/SPEC.md`, **señala la contradicción** antes de actuar. La orden del
   usuario gana, y al terminar actualizas el ID correspondiente de `docs/SPEC.md`.

### 2.2 Antes de editar
- Cambio de 1 archivo y obvio → hazlo directamente.
- Cambio de 2+ archivos, migración de BD o cambio de contrato → muestra un **plan breve**
  (archivos afectados + qué cambia en cada uno) y espera confirmación.
- Si la orden es ambigua → haz **una** pregunta concreta, no supongas.

### 2.3 Después de editar
Responde siempre con este formato, sin más texto:
```
HECHO: <una línea>
ARCHIVOS: <lista de rutas tocadas>
PENDIENTE/RIESGOS: <solo si hay; si no, omitir>
```
- Corre los tests del módulo tocado (`pytest tests/<modulo>`) y reporta solo si fallan.
- Si cambiaste modelos → genera la migración Alembic en el mismo cambio.

### 2.4 Vocabulario de órdenes del usuario
| Orden | Significado |
|---|---|
| `fase N` | Implementa la fase N del plan (sección 6 de SPEC). No avances a la N+1. |
| `implementa <ID>` | Implementa ese requisito y nada más. |
| `cambia <ID>: ...` | Modifica el requisito, el código que lo implementa y actualiza SPEC. |
| `fix: ...` | Corrige el bug descrito con el diff más pequeño posible. |
| `solo plan` | No edites nada; devuelve el plan. |
| `explica <archivo/ID>` | Solo explicación, cero cambios. |
| `revisa` | Revisión de código del último cambio; lista problemas, no los corrijas. |

## 3. Reglas técnicas no negociables
- **Nunca `DELETE` físico.** Soft delete (`eliminado_en`) + registro en `log_auditoria`.
- **Todo en UTC** en BD (`TIMESTAMPTZ`). Conversión a la zona del doctor solo en la UI y en mensajes.
- **Datos médicos cifrados** en la capa ORM (ver `SEG-01`). Nunca en logs, nunca en prompts de error,
  nunca en mensajes de excepción.
- **El webhook responde HTTP 200 en < 1 s.** Todo trabajo pesado va a Celery.
- **Antisolapamiento de citas por constraint de BD** (ver `DAT-05`), no solo por lógica de aplicación.
- **Secretos solo por variables de entorno** (`.env` nunca se versiona; mantener `.env.example`).
- **La UI Flet nunca se conecta a la BD**; consume `api_core` por HTTP.

## 4. Convenciones de código
- Python 3.11+, type hints obligatorios, `ruff` + `ruff format`.
- Código, variables y tablas en **español sin acentos** (`paciente`, `fecha_hora_inicio`).
  Comentarios y docstrings en español.
- Estructura: ver `SPEC.md §1.3`. Patrón repositorio: los routers no hablan con SQLAlchemy directamente.
- Tests con `pytest` + `pytest-asyncio`. Las llamadas a Gemini, Meta y Google se **mockean** siempre.

## 5. Comandos
```bash
docker compose up -d            # levanta postgres, redis, api_core, api_webhooks, worker, beat
alembic upgrade head            # migraciones
pytest                          # tests
ruff check . && ruff format .   # lint/format
```
