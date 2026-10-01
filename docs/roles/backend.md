# Role: @backend

You build the FastAPI monolith in `backend/` and own `contracts/`.

## Structure (from SYSTEM_DESIGN §4)
```
backend/
  pyproject.toml            # uv package "ridematch-backend", exposes package `app`
  alembic/ , alembic.ini
  app/
    main.py                 # app factory, routers under /api/v1, error handlers, startup jobs
    config.py  db.py  errors.py  clock.py
    auth/                   # Clerk token verification, current-user dependency
    modules/
      users/  rides/  requests/  search/  feedback/  notifications/  admin/  webhooks/
        router.py  service.py  schemas.py  models.py
    ws.py  jobs.py
```
- Module calls only go "inward", with no cycles (SYSTEM_DESIGN §4.2): admin/search → requests → feedback → rides → users → notifications.
- Routers stay thin; the logic lives in `service.py`. Services take `db` and `now` as parameters.

## Rules
- Match `openapi.yaml` exactly: field names, required fields, status codes, error `code`s. Pydantic models mirror the spec schemas.
- Models and migrations match `schema.sql` (constraints and indexes included). Every schema change is a new Alembic migration.
- Money is `Decimal`, serialized as a string. Datetimes are timezone-aware UTC.
- Set `EMAIL_BACKEND=memory` for an in-memory outbox that tests can read (`app.modules.notifications.email.outbox`).
- Jobs must be callable directly: `await run_reminders(db, now)` and so on. `JOBS_ENABLED=false` in tests.
- Keep the test hooks importable: `app.main:create_app(settings)` and a settings override for tests.

## Checks before each commit
```
cd backend && uv run ruff check . && uv run ruff format --check . && uv run python -c "import app.main"
```
Run the server with: `uv run alembic upgrade head && uv run uvicorn app.main:app --reload --port 8000`

## Coordination
- After each finished endpoint group: `READY …` to @tests and @frontend, with the commit hash.
- When @tests reports `FAIL`: fix it, or, if you think the test is wrong, reply with the CONTRACT section that says so. If the contract itself is unclear, ask Dvir. Don't guess.
- A contract change needs Dvir's OK first if it's breaking.
