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
| Liveness | `GET /api/v1/health` → `{"status":"ok"}`, no I/O | Docker `HEALTHCHECK`, Render health check, uptime monitor |
| Readiness | `GET /api/v1/ready` → 200 `{status, db: true, redis}` or 503 `NOT_READY` | manual check after a deploy |

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

## Deploy on Render

`render.yaml` (repo root) is a Render Blueprint on the free tier: the API (`ridematch-api`,
Docker, 1 instance), Key Value (`ridematch-kv`) and the frontend Static Site (`ridematch-web`, SPA
rewrite, CSP/HSTS/`nosniff`/Referrer-Policy/`frame-ancestors 'none'`), all in Frankfurt. Postgres is
**Neon**'s free tier (Render's free Postgres is deleted after 30 days). Every production variable is
listed in `.env.example` under "Production". The only cost is the domain.

Free-tier limits: the API sleeps after ~15 min idle and the first request wakes it (~1 min), so an
uptime monitor on `/api/v1/health` keeps it awake. Neon's free compute (100 CU-hours/month) only
lasts if the database can scale to zero, so nothing polls it: Render's health check is `/health`
(no DB), and `JOBS_ENABLED=false` turns off the jobs loop (reminders, auto-complete, stale-cancel;
set it to `true` on `ridematch-api` to bring them back, which catches up on anything overdue). There is no pre-deploy step, so
`alembic upgrade head` runs in the start command (`dockerCommand`), and no Shell, so admin tasks
run from your machine against Neon. To leave the free tier: `plan: starter`, move the migration to
`preDeployCommand`.

**Before the first deploy (outside Render)**
1. Pick the domain. Replace every `ridematch.example` in `render.yaml` with it (the API URLs, the
   Clerk issuer and the CSP), run `bash scripts/check-all.sh`, commit, push `main`.
2. Clerk: create the **production** instance for `<domain>` and add its DNS records
   (`clerk.<domain>` etc.). Note the `pk_live_`/`sk_live_` keys and the **JWKS Public Key** (PEM).
   Allowed origin: `https://app.<domain>`.
3. SMTP: a provider account with `<domain>` verified (SPF/DKIM); note host, port, user, password.
4. Mapbox: a public token restricted to `https://app.<domain>`.
5. Sentry (optional): one backend and one frontend project; note both DSNs.
6. Neon: a project, Postgres 16, region AWS Frankfurt (`eu-central-1`), database `ridematch`. Copy
   the **direct** connection string (not the `-pooler` host: the pooler breaks asyncpg's prepared
   statements and the jobs' advisory lock) and change its query to `?ssl=require` (asyncpg rejects
   `sslmode` and `channel_binding`): `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/ridematch?ssl=require`.

**Create the services**
1. Render → New → **Blueprint** → connect the GitHub repo, branch `main`. Render reads
   `render.yaml` and asks for every `sync: false` value: `DATABASE_URL` (Neon, above), the Clerk keys, PEM and webhook secret
   (enter a placeholder `whsec_` value for now if the endpoint doesn't exist yet), the SMTP
   settings, `EMAIL_FROM`, the Sentry DSNs, `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_MAPBOX_TOKEN`.
2. Apply. Render creates Key Value, builds the image, and the start command runs
   `alembic upgrade head` against Neon, then starts uvicorn and waits for `/api/v1/health` to return 200. If the
   API refuses to start, its log lists every invalid production setting at once.
3. Custom domains: `api.<domain>` on `ridematch-api`, `app.<domain>` on `ridematch-web`. Add the
   DNS records Render shows; it issues the TLS certificates.
4. Clerk → Webhooks: endpoint `https://api.<domain>/api/v1/webhooks/clerk`, events `user.updated`
   and `user.deleted`. Put its signing secret in `CLERK_WEBHOOK_SIGNING_SECRET` on `ridematch-api`
   (saving redeploys it).
5. Sign up on `https://app.<domain>`, finish onboarding, then make yourself admin from this folder
   (Git Bash; the Neon URL from step 6):
   `DATABASE_URL='<neon url>' uv run python -m app.admin_cli grant <your email>`.
6. An uptime monitor (e.g. UptimeRobot) on `https://api.<domain>/api/v1/health`, every 5 min (not
   `/ready`: its DB query would keep Neon awake).

**Check the deploy**
- `curl https://api.<domain>/api/v1/health` → `{"status":"ok"}`; `/ready` → `"status":"ready"`;
  `/docs` → 404.
- `curl -I https://app.<domain>/app/passenger/search` → 200 (the SPA rewrite) with the CSP, HSTS, `nosniff` and Referrer-Policy
  headers.
- Sign in, post a ride, see a live update; the browser console shows no CSP violations.

**Every later release:** `bash scripts/check-all.sh`, push `main`. Only the changed side rebuilds
(`buildFilter`). A failed migration or a `/ready` that never turns 200 aborts the deploy and the
old version keeps serving.

**Rollback:** Render → `ridematch-api` → Events → an earlier deploy → **Rollback**. Code only:
the database is not downgraded, which is why migrations are expand/contract.

**Keep:** `numInstances: 1`, no autoscaling, and no `--workers` (§4 of
the plan). `ADMIN_EMAIL` stays unset. Changing a `VITE_*` value needs a frontend redeploy; it's
baked into the bundle.

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
