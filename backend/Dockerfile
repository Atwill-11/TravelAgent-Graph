FROM python:3.11-slim

WORKDIR /app

ARG APP_ENV=production

ENV APP_ENV=${APP_ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && pip install --upgrade pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN uv venv && . .venv/bin/activate && uv pip install -e .

COPY . .

RUN useradd -m appuser \
    && mkdir -p /projectlogs \
    && chown -R appuser:appuser /app /projectlogs
USER appuser

EXPOSE 8000

RUN echo "Using ${APP_ENV} environment"

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 