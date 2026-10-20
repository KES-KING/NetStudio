FROM python:3.12-slim-bookworm AS runtime
ARG NETSTUDIO_BUILD_REVISION=unknown
ENV NETSTUDIO_BUILD_REVISION=${NETSTUDIO_BUILD_REVISION}
LABEL org.opencontainers.image.revision=${NETSTUDIO_BUILD_REVISION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:${PATH}"

RUN python -m venv /opt/venv \
    && addgroup --system --gid 101 netstudio \
    && adduser --system --uid 100 --ingroup netstudio --home /app netstudio

WORKDIR /app

COPY LICENSE /app/LICENSE
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
RUN pip install --no-cache-dir /app/backend

COPY --chown=netstudio:netstudio backend/alembic.ini /app/backend/alembic.ini
COPY --chown=netstudio:netstudio backend/migrations /app/backend/migrations

USER netstudio

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--ws-max-size", "16384", "--no-access-log"]
