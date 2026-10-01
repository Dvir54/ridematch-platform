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
