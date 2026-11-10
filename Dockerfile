# Imagen unica para api_core, api_webhooks, worker, beat y ui (cambia el comando).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/agenda

COPY pyproject.toml ./
COPY app ./app
COPY ui ./ui
RUN pip install ".[ui]"

COPY alembic.ini ./
COPY migrations ./migrations

# Sin privilegios de root dentro del contenedor.
RUN useradd --system --uid 10001 --no-create-home agenda
USER agenda

CMD ["uvicorn", "app.api_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
