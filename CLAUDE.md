# RideMatch: rules for the session

Phases 0–6 were built by three parallel sessions (@backend, @frontend, @tests) in worktrees; that setup is retired.
From Phase 7 on, **one** Claude Code session works in `C:\Users\dvir5\Projects\ridematch-platform` on branch `main` and owns every folder:
`backend/`, `frontend/`, `tests/`, `contracts/`, `.github/`, `scripts/`.
Dvir decides anything not covered here. Root files (`CLAUDE.md`, `PLAN.md`, `docs/`, `docker-compose.yml`, `.claude/`, `.gitignore`, `.env.example`) change only with his OK.

## Source of truth
- `contracts/openapi.yaml` gives the shapes, `contracts/CONTRACT.md` gives the behavior, and the Alembic migrations (`backend/alembic/versions`) give the DB. `contracts/schema.sql` is the verified reference: `tests/migrations` keeps it identical to `alembic upgrade head`, so a schema change updates both.
- Read only the CONTRACT/openapi sections the current chunk needs.
- The contract wins over assumptions. If it's ambiguous or wrong, **stop and ask Dvir**. Never quietly implement your own interpretation.
- A contract change: bump the version (CONTRACT.md §1), commit it on its own (`contract: …`), and keep backend, frontend types (`npm run gen:api`) and tests in step in the same chunk.

## Work order
- Work chunk by chunk from `PLAN.md` (Phases 7–8). Do only the **current** chunk.
- When the chunk is done: run its checks, commit, then stop and give Dvir a summary of at most 5 lines (done / blocked / anything he must decide). Don't start the next chunk until Dvir says so; he runs `/clear` in between.

## Budget
Tokens are limited. Keep each chunk lean:
- Scope: only the chunk's PLAN items. No extra hardening, audits, generators or smoke scripts. Propose extras in one line instead.
- Reading: read only what the chunk needs. Don't re-read files already in context. Use `grep`/`sed -n` ranges over whole-file reads.
- Checks: while working, run only the tests/files you touched, piped through `| tail -20`. Run the area's full check once, before the chunk's final commit. The full pytest suite (~8–12 min) runs only at a phase gate, in the background.

## Checks (before committing)
- Backend: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run python -c "import app.main"`
- Frontend: `cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run build`
- Tests: `cd tests && uv run pytest -q <files you touched>`. Always read the pass/**skip** count: an unreachable DB skips tests and still exits 0.

## Git
- Work on `main` only. Commit locally at every meaningful step; small, focused, conventional commits (`feat(…)`, `fix(…)`, `test(…)`, `contract: …`, `chore: …`).
- **Dvir pushes `main`** (`.claude/settings.json` denies it to Claude). Never rebase, force-push or `reset --hard`.
- Don't commit red code, except a failing test that documents a real bug, marked `xfail(strict=True)` with the reason.
- Never commit `.env` or secrets. Never read `.env`; `.env.example` lists every key.
- GitHub Actions is blocked on the account (support ticket pending): gates are checked locally.

## Dev machine
- Native **Windows**, shell is **Git Bash**. Forward slashes; no symlinks; don't rely on `chmod` or Unix-only tools.
- Keep LF line endings (`.gitattributes` enforces this). Python's `write_text` on Windows writes CRLF; write bytes or use the Write tool.
- `docker compose up -d` (from this folder) runs Postgres (`ridematch`, `ridematch_test` on host port 5434) and Redis (6379). If `docker` fails, tell Dvir.
- **Use `127.0.0.1`, not `localhost`, for Postgres/Redis**: Docker's IPv6 forward hangs on this machine. For tests: `TEST_DATABASE_URL=postgresql+asyncpg://ridematch:ridematch@127.0.0.1:5434/ridematch_test TEST_REDIS_URL=redis://127.0.0.1:6379/15`.
- Dev servers: backend `cd backend && uv run uvicorn app.main:app --port 8000`; frontend `cd frontend && npm run dev` (:5173, app routes under `/app`). Tests run in-process.

## Shared conventions
- Backend: Python 3.12, FastAPI, SQLAlchemy 2 (async) + asyncpg, Alembic, Pydantic v2, `uv`, `ruff`.
- Frontend: React + Vite + TypeScript (strict), React Router, TanStack Query, Clerk React SDK, Mapbox Geocoding, Tailwind CSS, Vitest, MSW.
- Tests: pytest + pytest-asyncio + httpx (in-process ASGI), Playwright for E2E, Schemathesis for fuzzing.
- Time: every time-dependent backend function takes an injectable clock (`now`). Never call `datetime.now()` deep in business logic.
