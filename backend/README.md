# ridematch-backend

The RideMatch API: one FastAPI process, mounted under `/api/v1`.
Contracts live in `../contracts/` and win over anything here.

## Run

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

`.env` is read from the repo root (one level up), so `uv run` picks up the same file the
frontend's Vite config uses. Every setting has a default, so the app imports without a `.env`.

## Checks

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run python -c "import app.main"
```

## Production image

`backend/Dockerfile` builds a non-root `python:3.12-slim` image from `uv.lock` (no dev deps).
It defaults to `APP_ENV=production`, so it refuses to start until every production setting is
valid (`app/config.py: production_problems`; all problems are listed at once).

```bash
docker build -t ridematch-backend backend
bash scripts/check-prod-image.sh     # build, migrate, start and probe it against compose
```

The start command is fixed in the image: **one** uvicorn process, no `--workers`
(`--ws-max-size 65536 --timeout-graceful-shutdown 20 --proxy-headers`). The WebSocket registry
and the jobs loop live in that process, so the host must run exactly one instance that never
sleeps. Job passes take a Postgres advisory lock, so the brief two-process overlap of a deploy
can't double-send reminders.

| Check | Path | Use |
|---|---|---|
| Liveness | `GET /api/v1/health` → `{"status":"ok"}`, no I/O | Docker `HEALTHCHECK` |
| Readiness | `GET /api/v1/ready` → 200 `{status, db: true, redis}` or 503 `NOT_READY` | host deploy gate, uptime monitor |

## Migrations and releases

Alembic (`alembic/versions`) defines every database, the test DB included; `contracts/schema.sql`
is the reference that `tests/migrations` keeps identical to `alembic upgrade head`.

- **Release:** the host runs `alembic upgrade head` as its pre-deploy step, before the new
  version takes traffic. A failing migration aborts the deploy and the old version keeps running.
  To preview the SQL: `uv run alembic upgrade head --sql`.
- **Expand/contract only:** for the minute both versions run, the old code must still work on the
  new schema. Add columns nullable or with a default, backfill, switch the code, and drop the old
  thing in a later release.
- **A data migration** gets a test that upgrades to the revision before it, seeds rows, upgrades,
  and asserts the result.
- **Production never downgrades;** fix forward with a new revision.
- **Take a backup or snapshot** before any destructive migration (a drop or a type change).
- A new revision also updates `contracts/schema.sql`, or `tests/migrations` fails.

## Admin tasks (run on the server)

```bash
python -m app.admin_cli grant <email>       # make an onboarded user an admin (the only way in production)
python -m app.admin_cli revoke <email>
python -m app.admin_cli anonymise <email>   # a deletion request made outside Clerk
```

## Test hooks

- `app.main:create_app(settings)` builds an app from an explicit `Settings` instance.
- With `APP_ENV=test`, `Settings.effective_database_url` resolves to `TEST_DATABASE_URL`.
- `app.clock:utc_now` is a FastAPI dependency; override it to freeze time.
- `EMAIL_BACKEND=memory` collects mail in `app.modules.notifications.email.outbox`.
- Migrations target `Settings.effective_database_url`, so `APP_ENV=test uv run alembic upgrade head`
  migrates `ridematch_test`.

## Layout

```
app/
  main.py      app factory, routers, error handlers
  config.py    pydantic-settings
  db.py        engine/session, declarative Base
  errors.py    the {code, message, details} envelope
  clock.py     injectable now()
  schemas.py   shared primitives (Money, UtcDatetime, Latitude, Longitude)
  auth/        Clerk token verification + current-user dependencies
  modules/
    users/ rides/ requests/ feedback/ notifications/
```

Module calls only go inward (SYSTEM_DESIGN §4.2):
admin/search → requests → feedback → rides → users → notifications.
