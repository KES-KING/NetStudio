FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN python -m venv /opt/venv \
    && addgroup --system stocc \
    && adduser --system --ingroup stocc --home /app stocc

WORKDIR /app

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
RUN pip install --no-cache-dir /app/backend

COPY --chown=stocc:stocc backend/alembic.ini /app/backend/alembic.ini
COPY --chown=stocc:stocc backend/migrations /app/backend/migrations

USER stocc

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

