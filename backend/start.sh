#!/bin/sh
# Render free-tier start command (render.yaml `dockerCommand: sh start.sh`): the free plan has no
# pre-deploy step, so the release runs here. A failed migration exits before uvicorn starts, the
# health check never passes, and the deploy aborts with the old version still serving.
# Kept in a script because Render does not pass a quoted `sh -c "..."` dockerCommand through intact.
set -e
alembic upgrade head
# Same flags as the Dockerfile CMD.
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --ws-max-size 65536 \
    --timeout-graceful-shutdown 20 --proxy-headers --forwarded-allow-ips='*' --no-server-header
