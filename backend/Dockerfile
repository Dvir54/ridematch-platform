# RideMatch API: one uvicorn process, one worker.
# Build from backend/:  docker build -t ridematch-backend backend
# Release step (before traffic):  alembic upgrade head

# ── build: resolve the locked dependencies into /app/.venv ──
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so a code-only change reuses this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md alembic.ini start.sh ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable

# ── runtime: no uv, no build tools, non-root ──
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 ridematch
WORKDIR /app
COPY --from=build --chown=ridematch:ridematch /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PORT=8000
USER ridematch
EXPOSE 8000

# Liveness only: /health does no I/O, so a database outage never restarts the container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4)"

# No --workers: the WebSocket registry and the jobs loop live in this one process (§4).
# 64 KiB WS frames (CONTRACT.md §6); 20 s for sockets to close on deploy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --ws-max-size 65536 --timeout-graceful-shutdown 20 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
