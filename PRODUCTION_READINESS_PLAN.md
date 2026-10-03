# RideMatch: Production Readiness Plan (rev. 2)

## 0. Approved: start here (status as of 2026-10-03)

Dvir approved this plan. A new session implements it from this section plus §15–§19. The rest of the file is the reasoning behind it.

### Decisions (§18 answered)

- **D1 Host: Render.**
  - One web service: 1 instance, 1 uvicorn process, never sleeps.
  - Render Postgres and Render Key Value.
  - A Static Site for the frontend.
  - The health check path is `/api/v1/ready`, and the pre-deploy command is `alembic upgrade head`.
  - Config goes in `render.yaml` with `sync: false` for secrets.
  - **Don't** create the Render account or deploy.
- **D2 Sentry: yes,** for the backend and frontend, errors and alerts only.
  - No tracing, no session replay, `send_default_pii=False`.
  - Before writing the scrubbing, inspect what can reach Sentry from FastAPI exceptions, React errors, HTTP requests, auth failures and WebSocket errors.
  - Scrub (`before_send`) the `Authorization` header, cookies, query strings, request bodies, the WS `auth` token, emails, and the `svix-*` headers.
  - Test that a captured event contains none of these.
  - Add Sentry to the data inventory (§12) as a processor.
- **D3 Phone: stop collecting it.**
  - Remove it from onboarding, Profile, the admin user view, the backend schemas and the service.
  - Add Alembic migration `0002` to drop `users.phone`. `schema.sql` already drops it.
  - Update the tests and MSW mocks.
  - Remove `frontend/src/lib/phone.ts` if nothing uses it any more.

### Additional requirements from Dvir

- **Date of birth:** keep the 18+ check as it is. Write down in §12 whether the stored DOB could later shrink to an "18+ verified" flag, but **don't change the schema for it**.
- **Legal:** don't write the terms or privacy text. Build the `/terms` and `/privacy` routes and links with clearly marked placeholders. Keep §12's data inventory accurate, with Sentry and the phone removal reflected.
- **Limits:** a 64 KiB body limit (413) and a 64 KiB WebSocket frame cap. **No** per-user 429 rate limiting yet.
- **SMTP:** 10 s timeout, commit first, then dispatch, with failures logged without the address. No job or outbox infrastructure.
- **Keep the Postgres advisory lock** around job passes.
- No unrelated refactors.

### Done so far

- `8889f3c`: this plan.
- `3d9709f` **contract 0.5.0 (D22)**: `openapi.yaml`, `CONTRACT.md` (§2, §4, §5, §6, D22) and `schema.sql` are updated, and `frontend/src/api/schema.d.ts` is regenerated. **The contract is the spec for steps 2–9.** The code doesn't implement it yet, so **`main` is red** (frontend typecheck, tests) until the work below lands. Don't push before then.

Details §19 and D22 leave open, decided now:

| Area | Decision |
|---|---|
| WebSocket | `{"event":"auth","token":…}` first, 10 s timeout (`WS_AUTH_TIMEOUT_SECONDS`), the server replies `{"event":"ready"}`. A bad `Origin` closes with 4403. A `?token=` query parameter is ignored. |
| `/health` | `{"status":"ok"}`, no I/O. |
| `/ready` | 200 `{status:"ready", db:true, redis}`, or 503 `NOT_READY`. |
| Anonymisation | `name="Deleted user"`, `email=deleted-<id>@deleted.invalid`, `clerk_user_id=deleted_<id>`, `gender`/`vehicle`/`preferences` null, `date_of_birth=1900-01-01`, `is_active=false`. |
| CLI | `python -m app.admin_cli grant\|revoke\|anonymise <email>` |

### Work order

The contract step (§19 step 1) is done. Do §19 steps 2–9, plus the D2 and D3 work above. **Dvir asked for all phases in one run, not one chunk per conversation**, which overrides CLAUDE.md's "stop after each chunk".

After each phase:
1. run the relevant tests;
2. run the frontend build;
3. run the backend checks;
4. run audits where relevant;
5. check nothing regressed;
6. commit.

**Before finishing:**
- [ ] full pytest suite (in the background)
- [ ] frontend production build
- [ ] `alembic check`
- [ ] `alembic upgrade head` on a clean database
- [ ] production config validation
- [ ] WebSocket auth flow
- [ ] `/health` and `/ready`
- [ ] admin CLI
- [ ] email after commit and the timeout
- [ ] Sentry receives no sensitive data
- [ ] `pip-audit` and `npm audit`
- [ ] a final readiness pass
- [ ] update this file's status

**Then report:**
1. what changed;
2. which checks passed;
3. remaining blockers;
4. what Dvir must configure manually;
5. the exact Render deployment steps.

Then stop.

Repo-side deploy artifacts to create:
- `backend/Dockerfile` and `.dockerignore`
- `render.yaml`
- the production section of `.env.example`
- `scripts/check-all.sh`
- a local production-like validation script (build the image, run it against the compose Postgres and Redis with `APP_ENV=production`-style settings, hit `/health` and `/ready`)
- the migration and release runbook in `backend/README.md`

Edit `CLAUDE.md` wording only where §5 says to (Alembic is the DB source of truth).

Audit: 2026-10-03 · `main` @ `c4d871c` · contract 0.4.9 · **plan only; no application code has been changed.**

Rev. 2 adds a precise analysis of every blocker and deployment risk, a hosting comparison, a data inventory and a concrete deployment architecture. It ends with the four lists asked for in §14–§17.

---

## 1. Executive summary

The application code is ready for production: it's layered, typed and contract-driven, with about 900 API tests, Schemathesis fuzzing, an E2E flow, a clean dependency audit (`pip-audit` 0, `npm audit` 0) and no secrets in git history. What's still missing is the production envelope:

- fail-fast production configuration;
- a safe admin bootstrap;
- the session token out of the WebSocket URL;
- Alembic as the tested source of the schema;
- separate liveness and readiness endpoints;
- non-blocking email;
- a deployment artifact;
- legal pages and a data-deletion path.

Everything fits a **single instance, single process** deployment. Nothing needs horizontal-scaling work before launch.

## 2. Architecture (as built)

| Area | Actual |
|---|---|
| Frontend | React 19, Vite 8, TS 5.9 strict, React Router 7, TanStack Query 5, Clerk React 5, Tailwind 4, Vitest + MSW. npm. Types are generated from `contracts/openapi.yaml`. |
| Backend | Python 3.12, FastAPI 0.142, Uvicorn 0.54, SQLAlchemy 2.1 async + asyncpg, Alembic, Pydantic 2.13, PyJWT. uv (`uv.lock`). Code lives in `app/modules/<domain>/{models,schemas,service,router}.py`. |
| Data | PostgreSQL 16 (no extensions). Redis 7 holds only the WS presence counters (`ws:online:*`). `online_count` is read by **nothing** in production code, so the app works fully without Redis. |
| Auth | Clerk session JWT sent as `Authorization: Bearer`. RS256 verified via JWKS or the `CLERK_JWT_KEY` PEM, with `iss`, `azp` and `exp` checked. Then the `users` row is loaded. No cookies. |
| AuthZ | The `is_admin` DB flag guards `/admin/*`. Ownership checks live in the services. The plate is shown only to the driver and approved passengers. |
| Real-time | `GET /api/v1/ws?token=…`. The sockets sit in a per-process dict (`WsRegistry`). Pushes are queued on the DB session and sent after commit. |
| Jobs | An in-process asyncio loop every 60 s: reminders, auto-complete, stale-cancel. Each pass is one transaction. |
| Email | `EMAIL_BACKEND=console\|smtp\|memory`. Sent **inline, before commit**. Only 3 triggers send email: `welcome`, `request_approved`, `request_rejected`. |
| External | Clerk (JWT/JWKS, Backend API ban/unban, Svix webhooks), Mapbox Geocoding v6 (browser only), SMTP, Google Fonts (browser). No AI, no uploads. |
| CI/CD | `ci.yml` exists, but GitHub Actions is blocked on the account. No deploy config yet. |

No folder reorganisation is proposed.

---

## 3. Authentication and Clerk (B-1, B-6)

### 3.1 Fail-fast production auth configuration (B-1)

**Current.**
- `Settings` (`app/config.py`) defaults every field. `ClerkVerifier.verify` (`app/auth/clerk.py:96-112`) sets `verify_iss = bool(CLERK_ISSUER)` and checks `azp` only `if parties`. **So an empty `CLERK_ISSUER` or `CLERK_AUTHORIZED_PARTIES` silently turns those checks off.**
- With neither `CLERK_JWT_KEY` nor `CLERK_JWKS_URL` set, every request gets a 401. That fails closed, but only at request time.
- `DATABASE_URL` and `REDIS_URL` default to localhost.
- `EMAIL_BACKEND=memory` grows an in-memory list forever.
- Nothing distinguishes a dev Clerk instance from a production one.

**Why it's a risk.** One missing or mistyped variable in a host dashboard weakens token validation, and the app gives no sign of it. Using a dev Clerk instance in production (its keys work) would put production users in a dev tenant.

**Recommendation.** Add a `model_validator(mode="after")` on `Settings` that runs only when `APP_ENV=production`. It collects **every** violation into one error, so the process exits at import (`app = create_app()`), the host marks the deploy failed and keeps the previous version. Rules:

| Variable | Production rule |
|---|---|
| `CLERK_ISSUER` | required. `https://`. Must **not** end in `.clerk.accounts.dev` (that's a dev instance). |
| `CLERK_JWT_KEY` | required, and must parse as an RSA public key (`cryptography.load_pem_public_key`). See the note below. |
| `CLERK_AUTHORIZED_PARTIES` | non-empty. Each entry `https://`, no `localhost`/`127.0.0.1`, no `*`. |
| `CORS_ORIGINS` | same rules. Each must also appear in `CLERK_AUTHORIZED_PARTIES`. |
| `CLERK_SECRET_KEY` | starts with `sk_live_`. |
| `CLERK_WEBHOOK_SIGNING_SECRET` | starts with `whsec_` and base64-decodes. |
| `DATABASE_URL`, `REDIS_URL` | set, and not localhost. |
| `EMAIL_BACKEND` | `smtp`, with `SMTP_HOST` set and `EMAIL_FROM` not `*.local`. |
| `ADMIN_EMAIL` | must be **empty** (see §3.2). |

In every environment, also normalise `postgres://` / `postgresql://` to `postgresql+asyncpg://`. Every host hands out the plain scheme. At startup, log one redacted line: env, issuer, parties, DB host.

*Why require the PEM in production.* With `CLERK_JWT_KEY`, verification needs no network: no JWKS fetch, no dependency on Clerk at request time, and the JWKS lock problem in §11.4 can't happen. The trade-off is that if the Clerk instance key is ever rotated, you update one secret and redeploy. Instance keys don't change on their own.

**Alternatives.**
- Accept `CLERK_JWKS_URL` as an alternative, requiring `https` and the same host as the issuer. More flexible, but it keeps the network path.
- Warn instead of fail. Rejected: you asked for fail-fast.

**Affects.** Backend config and deployment config. No contract, DB or frontend change.

**Test.** A new `tests/unit/test_settings_production.py`:
- a complete, valid production settings object passes;
- each rule fails, with the variable name in the message (parametrised);
- several violations are all reported at once;
- `development` and `test` stay permissive;
- URL normalisation is covered.

Build settings with `_env_file=None` so the local `.env` can't interfere.

**When.** **Must, before production.**

### 3.2 Admin provisioning (B-6)

**Current** (`users/service.py:132-135`, CONTRACT §4). At onboarding, if the token's `email` claim equals `ADMIN_EMAIL` **and no admin exists**, the user is created with `is_admin=true`. Safety depends on one Clerk setting, "verify email at sign-up". Two gaps:

1. If the production Clerk instance is misconfigured (verification optional), the first person to register that address becomes admin.
2. The bootstrap re-arms whenever no admin exists, for example after the only admin is revoked.

There's also a related squatting risk: without verification, anyone can register your address first and get `EMAIL_ALREADY_EXISTS` for you.

**Recommendation.** **There is no automatic admin promotion in production.**
- The validator rejects `ADMIN_EMAIL` when `APP_ENV=production` (§3.1).
- The onboarding code also checks `not settings.is_production` before honouring it (belt and braces).
- Add a CLI, `python -m app.admin_cli grant <email>` / `revoke <email>`. It's idempotent, refuses unknown or deactivated users, prints the result, and exits non-zero on failure.
- Run it once through the host's one-off shell, after you've signed up and onboarded in production.
- The `ADMIN_EMAIL` bootstrap stays for dev and test only, so the existing tests and local flow are unchanged.
- Clerk production keeps "verify email at sign-up" on regardless (§3.3), because email identity is also used for `EMAIL_ALREADY_EXISTS`.

**Alternatives.**
- **`ADMIN_CLERK_USER_ID`** env var, bound to Clerk's immutable `user_…` id. Also safe, and needs no shell. But it's still an auto-promotion path, and it needs a redeploy after you sign up to learn your id.
- An `email_verified` session-token claim, checked before bootstrapping. That's defence in depth, but it still auto-promotes.

**Affects.**
- Contract: §4 wording ("development only; production admins via CLI").
- Backend: new CLI module plus the guard.
- Deployment: one runbook step.
- No DB or frontend change.

**Test.**
- CLI tests: grant an existing user, grant an unknown email (exit 1), revoke, run twice (idempotent).
- Onboarding with a production-flagged settings object never sets `is_admin`.
- The validator rejects `ADMIN_EMAIL` in production.

**When.** **Must, before production.**

### 3.3 Required Clerk production configuration (Dvir, in the Clerk dashboard)

1. Create a **production instance** for your domain and add the DNS CNAMEs Clerk lists (`clerk.`, `accounts.`, email DKIM).
2. Email address: **required**, **verify at sign-up: on**.
3. Session token customisation: `{"email": "{{user.primary_email_address}}"}`. Without it, every API call returns 401 with a message that names this.
4. Google sign-in, if wanted, needs **your own** Google OAuth credentials (production instances don't use Clerk's shared ones).
5. Attack protection / bot protection: on.
6. Webhook endpoint `https://api.<domain>/api/v1/webhooks/clerk`, events `user.updated` and `user.deleted`. Its signing secret goes into `CLERK_WEBHOOK_SIGNING_SECRET`.
7. API Keys page:
   - `pk_live_…` → `VITE_CLERK_PUBLISHABLE_KEY`
   - `sk_live_…` → `CLERK_SECRET_KEY`
   - the JWT public key (PEM) → `CLERK_JWT_KEY`
   - the Frontend API URL → `CLERK_ISSUER`

---

## 4. WebSockets and background jobs: single process (B-2)

**Is 1 instance × 1 worker technically safe for this architecture?** **Yes**, with the two conditions below.

Why it works:
- Every socket lives in the one `WsRegistry`, so every after-commit push reaches every connected recipient.
- The jobs loop runs once per minute in one place. Each pass is one transaction, so a SIGTERM mid-pass rolls back cleanly. Reminders are idempotent (they skip rides that already have a `ride_reminder` row).
- A single asyncio process handles a launch-scale load comfortably: the work is I/O-bound, RS256 verification takes sub-milliseconds, and an idle socket costs a few KB.

**Condition 1: deploy overlap.** Zero-downtime deploys on all three hosts start the new instance before stopping the old one, so for a few seconds to a minute **two processes run**. During that window:
- Both jobs loops can run the same pass. The reminder dedupe isn't atomic across processes, and auto-complete and stale-cancel would each send their notifications twice. This causes duplicate notifications and duplicate "request declined" emails, not data corruption.
- A socket on the old process misses pushes for writes handled by the new one. It reconnects when the old process shuts down, and REST stays the source of truth.

**Fix (small, no new infrastructure):** wrap each `run_all` pass in `pg_try_advisory_xact_lock(<constant>)`. Whichever process gets the lock runs the pass, and the other skips that minute. This also makes multi-instance safe for jobs later.

**Condition 2: the process must never sleep or multiply.**
- The start command is `uvicorn app.main:app --host 0.0.0.0 --port $PORT` with **no `--workers`** and no gunicorn.
- Host instance count is pinned to 1, with autoscaling off.
- Sleeping or scale-to-zero must be off (Render free tier, Fly `auto_stop_machines`, Railway serverless). A sleeping process stops the jobs and drops every socket.
- `--ws-max-size 65536` caps inbound WS frames (the default is 16 MB, and the only inbound frame is the ping).
- `--timeout-graceful-shutdown 20` lets sockets close cleanly; clients reconnect with backoff.
- All of this is documented in `backend/README.md`.

**Limitations at launch:**
- A crash or restart means a short outage. The host restarts it, and clients reconnect with backoff.
- There's no redundancy against a host-node failure.
- Vertical scaling only.

**What would change for multiple workers or instances** (not now, since nothing requires it before release):
1. WS fan-out over Redis pub/sub. Each process subscribes and delivers to its local sockets. `WsRegistry.push` publishes instead of sending directly.
2. Jobs: the advisory lock above already covers this. Alternatively, run the jobs as a separate worker service with `JOBS_ENABLED=false` on the web instances.
3. Presence counters: make them TTL-based, so a crashed process doesn't leave stale counts.
4. Rate-limit state (if added) is already in Redis.

**Affects.** Backend (advisory lock, about 10 lines) and deployment config. No contract, DB or frontend change.

**Test.**
- Two sessions call `run_all` concurrently with the same `now`, and exactly one set of notification rows is written.
- A pass skipped while the lock is held writes nothing.

**When.** Single-process config: **must**. Advisory lock: **must** (cheap, and every deploy creates the overlap).

---

## 5. Alembic migrations (B-5)

**Current.**
- `tests/support/db.py::reset_schema` drops `public` and executes `contracts/schema.sql`.
- Production will run `alembic upgrade head` (`backend/alembic/versions/0001_initial_schema.py`, a hand mirror of schema.sql, with downgrade). **No test ever runs Alembic.**
- `alembic/env.py` takes the URL from `Settings.effective_database_url` (`APP_ENV=test` → `TEST_DATABASE_URL`). It calls `fileConfig()`, which reconfigures logging and disables existing loggers, and `asyncio.run()`, which can't run inside pytest's event loop.

**Why it's a risk.** About 900 tests verify a schema that production never gets. Any drift in a partial index, CHECK, trigger or default ships untested.

**Recommendation: Alembic becomes the source of truth for the database. `schema.sql` becomes a verified reference document.**

1. **Test DB is built by Alembic.**
   - `reset_schema` drops and recreates `public`, then runs `alembic upgrade head` in a **subprocess**: `uv run alembic upgrade head` with `cwd=backend` and `APP_ENV=test` plus `TEST_DATABASE_URL` in the env.
   - A subprocess avoids the `asyncio.run` and `fileConfig` side effects, and it's exactly the command the production release step runs. It costs about 2 s once per session.
   - `PRESERVED_TABLES` already keeps `alembic_version` out of the truncate step.
2. **New `tests/migrations/test_alembic.py`**, each case on a scratch schema or database:
   - **upgrade from empty**: `upgrade head` succeeds, and `alembic current` equals `alembic heads`.
   - **single head**: `alembic heads` returns exactly one revision, which guards against branch merges later.
   - **round trip**: `upgrade head` → `downgrade base` (only `alembic_version` remains) → `upgrade head`. This proves rollback scripts work.
   - **idempotent**: a second `upgrade head` is a no-op.
   - **models match migrations**: `alembic check` (autogenerate diff is empty, `compare_type=True` is already set).
   - **schema.sql parity**: build the reference into a separate schema (`SET search_path TO ref`, then run schema.sql) and compare catalog snapshots of `public` against `ref`:
     - columns (`information_schema.columns`: type, nullability, default)
     - constraints (`pg_get_constraintdef`)
     - indexes (`pg_indexes.indexdef` with the schema name stripped)
     - triggers (`pg_get_triggerdef`)
     - functions (`pg_get_functiondef`)

     This is pure SQL, so there's no `pg_dump` binary dependency on Windows.
   - **non-superuser**: run `upgrade head` as a role that has only `CREATE` on the schema. That's how managed Postgres app roles work, and it proves no superuser-only DDL. Today there are no extensions, and plpgsql functions are fine.
3. **Future migrations** (a documented rule, nothing to build now):
   - expand/contract only, so the old version keeps working during the deploy overlap;
   - a data migration gets a test that upgrades to N-1, seeds rows, upgrades to N and asserts;
   - production never downgrades; it rolls forward;
   - take a manual backup or snapshot before any destructive migration.
4. **Production procedure:**
   - the host's pre-deploy or release command runs `alembic upgrade head` before the new version takes traffic;
   - a failing migration aborts the deploy and the old version keeps running;
   - optionally review `alembic upgrade head --sql` first.

**Alternatives.**
- Keep schema.sql for tests and only add the parity test. That's smaller, but it leaves the tests on the non-production path, which contradicts your requirement.
- Delete schema.sql and generate it from Alembic. Simplest long-term, but `contracts/schema.sql` is named in CLAUDE.md and CONTRACT as a source of truth, so that wording changes either way (root files: your OK).

**Affects.**
- Tests (`tests/support/db.py`, new migration tests).
- `CLAUDE.md` and CONTRACT wording: "Alembic is the DB source of truth; schema.sql is the verified reference".
- No API, frontend or production schema change.

**Test.** The list above is the test. After the switch, the full pytest suite runs once in the background to prove the Alembic-built DB passes everything.

**When.** **Must, before production.**

---

## 6. WebSocket authentication (token in URL)

**Current.**
- `socketClient.ts:107` opens `${wsUrl}?token=<Clerk JWT>` (CONTRACT §6). The server reads `token` from the query in `ws.py`, verifies it once, then accepts pings.
- Uvicorn's `uvicorn.error` logger writes `"WebSocket /api/v1/ws?token=eyJ…" [accepted]` at INFO.
- The host's edge proxy may also record full URLs in its request logs.

**Why it's a risk.** A bearer credential sits in logs that are retained, searchable, possibly shipped to third parties, and readable by anyone with dashboard access. Clerk tokens live about 60 s, which limits replay, but credentials in logs is an OWASP-listed exposure, and the session id inside the token is longer-lived context.

**Recommendation: authenticate with the first message.**
1. The client connects to `wss://api…/api/v1/ws` with no query. On `open`, it sends `{"event":"auth","token":"<fresh getToken()>"}`.
2. The server `accept()`s and waits up to **10 s** (a setting, so tests can shorten it) for exactly one `auth` message. Then the current checks run:
   - invalid or expired token, no profile, a timeout, or any other first message → close **4401**;
   - deactivated account → close **4403**;
   - success → the server sends `{"event":"ready"}` and registers the socket.
3. Close codes, ping/pong and the push payload are all **unchanged**. The frontend's reconnect and backoff logic is unchanged apart from how the token is sent.
4. Also check the handshake `Origin` against `CORS_ORIGINS`, rejecting with 4403 or a refused accept. Browsers don't apply CORS to WebSockets, so this blocks other sites from opening sockets.

**Trade-offs.**
- **Benefits:** the token never touches a URL, proxy log or access log. No new endpoint, and no new Redis dependency (WS keeps working with Redis down, as today). It's a small change on both sides.
- **Costs:** an unauthenticated socket can exist for up to 10 s (mitigated by the timeout and the frame-size cap). It's a **breaking contract change to §6**. That costs nothing *before* launch, because no deployed clients exist. After launch, cached old bundles would need a dual-mode transition period, which is the main reason to do it now.

**Alternatives.**

| Option | Pros | Cons |
|---|---|---|
| Ticket: `POST /ws/ticket` (Bearer) returns a 30 s single-use opaque ticket in Redis; connect with `?ticket=` | What's in the URL is single-use and dead after connecting | One extra endpoint and round trip; Redis becomes a hard dependency for WS; more code |
| Token in `Sec-WebSocket-Protocol` | No URL exposure | A hack: the server must echo the subprotocol, and some proxies log headers |
| Cookie auth | Automatic | Clerk's `__session` cookie is bound to the app domain, not `api.`; adds CSRF/CSWSH surface |
| Keep the query token and filter uvicorn logs | Smallest change | Doesn't cover host proxy logs |

**Affects.**
- Contract: §6 and the `WsClientMessage`/`WsServerMessage` schemas in openapi.yaml (minor bump).
- Backend: `ws.py`.
- Frontend: `socketClient.ts`, plus `gen:api`.
- No DB or deployment change.

**Test.**
- Backend `tests/api/test_websocket.py`:
  - auth message → `ready` → ping/pong;
  - no auth before the timeout → 4401;
  - a bad token, a non-auth first message, or a legacy `?token=` without an auth message → 4401;
  - deactivated → 4403;
  - a foreign `Origin` is rejected.
- Push-equals-REST tests keep passing.
- A log test: capture all records during a connect and assert none contains the token.
- Frontend: `socketClient.test.ts` asserts the URL has no query and the first frame is `auth`, and that reconnect fetches a fresh token.
- E2E: the live-push flow still passes.

**When.** **Must, before production.** It's breaking, so it's cheapest before any clients exist.

---

## 7. Liveness and readiness

**Current.** `GET /health` runs `SELECT 1` through the request's DB session plus a Redis `PING`, and **always returns 200**: `{"status":"ok"|"degraded","db":bool,"redis":bool}`. So a host check can't tell when the DB is down. The only frontend reference is an MSW mock.

**Recommendation: separate the two.**

| Endpoint | Purpose | Checks | Response |
|---|---|---|---|
| `GET /api/v1/health` (liveness) | "Is the process serving HTTP?" | **nothing external**, no I/O | always `200 {"status":"ok"}` |
| `GET /api/v1/ready` (readiness) | "Can this instance do useful work?" | DB `SELECT 1` on a pooled connection with a **2 s** timeout. Redis `PING` with a 1 s timeout, **reported but not gating**. | `200 {"status":"ready","db":true,"redis":bool}`, or **503** with the error envelope `{"code":"NOT_READY","message":"Database unreachable.","details":[{"field":"db",…}]}` |

- **The DB should affect readiness.** Every endpoint except `/health` needs it, so an instance without a DB can't serve, and the host must not switch traffic to a new version that can't reach it.
- **Redis should not.** It only holds unread presence counters; the app degrades to nothing noticeable.
- **Liveness must not check the DB.** A DB outage isn't fixed by restarting the app, and a liveness check tied to the DB turns one outage into a restart loop.

**Where each is used:**
- host deploy and health check → `/ready`
- Docker `HEALTHCHECK` and Fly machine checks → `/health`
- external uptime monitor → `/ready`

Render has only one check path, used both to gate deploys and to monitor. Point it at `/ready`. During a DB outage Render may then restart the instance, which is harmless (it's stateless, and sockets reconnect) and the app is useless anyway in that state.

**Optional, can wait:** readiness also verifies `alembic_version` equals the code's head revision. The release step makes a mismatch unlikely.

**Alternatives.**
- Keep `/health` as is and add only `/ready`. That avoids one breaking change, but `/health` would keep doing I/O and returning a misleading 200.
- Make `/health` return 503. Simplest, but it mixes the two concerns.

**Affects.**
- Contract: `/health` response shape (breaking, minor bump), a new `/ready`, and the `NOT_READY` code in §5.
- Backend: `health.py`.
- Frontend: `gen:api` and the MSW handler.
- Deployment: the check paths.

**Test.**
- `/health` returns 200 with the DB unreachable: point settings at a closed port.
- `/ready` returns 200 when the DB is up and Redis is down.
- `/ready` returns 503 with the envelope when the DB is down.
- Both validate against openapi.yaml with the existing contract helper.
- Both are unauthenticated.

**When.** **Must, before production.** The host checks depend on it.

---

## 8. SMTP

**Current** (`notifications/email.py`, `notifications/service.py:111`).

| Question | Answer |
|---|---|
| Where is the connection created? | `_send_smtp`: a new `smtplib.SMTP(host, port)` per message, then `starttls()` and `login`, run via `asyncio.to_thread`. |
| Is there a timeout? | **No.** smtplib's default is the socket default, which is none. A stalled server blocks forever. An unreachable host waits for the OS TCP timeout (20 s to 2 min). |
| Does it block API requests? | It doesn't block the event loop (it's a thread). But `notify()` **awaits** it inside the request, **before commit**. So the response waits for SMTP, the DB connection stays checked out, and on **approve** the ride's `SELECT … FOR UPDATE` lock is held for the whole SMTP exchange, which blocks other approvals on that ride. Hung sends also fill the default thread pool. |
| What if the provider is unavailable? | The exception is logged (with the recipient address, which is PII in logs) and the request succeeds after the delay. The email is lost, with no retry. The in-app notification row is unaffected. |
| Should sending happen after commit? | **Yes.** Today an email can go out for a transaction that later fails to commit. |
| Should it move to a background job? | Eventually, as a durable outbox. Not needed for launch: the in-app notification is the durable record, and email is a courtesy copy. |

**Recommendation for launch (the simplest reliable option):**
1. `smtplib.SMTP(..., timeout=10)`. Use `SMTP_SSL` when `SMTP_PORT=465`, since some providers only offer implicit TLS.
2. **Queue on the session, send after commit.** Reuse the `ws_push` pattern:
   - `notify()` appends the `EmailContent` to `db.info["email_pending"]` instead of sending;
   - `commit_and_push()`, after a successful commit, hands each one to `asyncio.create_task(send_email(...))`, tracked in a module-level set so tasks aren't garbage-collected;
   - responses return immediately.
3. On app shutdown, the lifespan awaits the outstanding email tasks for up to 10 s.
4. Failure logs name the **user id**, not the address.

**Later (post-launch):** an `email_outbox` table written in the same transaction, drained by the jobs loop with retries and backoff. That's durable across restarts, but it's a schema change and it isn't needed yet.

**Alternatives.**
- FastAPI `BackgroundTasks`: only exists in request context, and the jobs loop also sends email, so it doesn't fit the service layer.
- `aiosmtplib`: a new dependency for no real gain at this volume.
- The provider's HTTP API instead of SMTP: fine, but provider-specific. SMTP keeps the provider swappable.

**Affects.** Backend only. No contract, DB, frontend or deployment change. `EMAIL_FROM` and `SMTP_*` are already documented.

**Test.**
- With the memory backend, nothing is sent when the transaction rolls back or raises before commit, and the email is sent after a successful commit. Tests await a small `email.drain()` helper.
- A fake slow backend shows the API response doesn't wait for it.
- Unit test that `smtplib.SMTP` is constructed with `timeout=10`, and `SMTP_SSL` is used on port 465.
- The existing notification-trigger tests (which check who gets emailed) keep passing once drained.

**When.** Timeout and after-commit: **must**. Outbox: **can wait**.

---

## 9. Rate limiting and request limits

**Current.** No rate limiting and no body-size limit (uvicorn has none). WS frames accept up to 16 MB.

**Endpoint analysis:**

| Class | Endpoints | Real risk today | Needs a limit? |
|---|---|---|---|
| Security-sensitive | No login, password, OTP or reset endpoints: **Clerk owns them** and has its own attack protection. `/users/me/onboarding` (once per user). `/admin/*` (admins only). | No brute-force surface in our API. | No |
| Public / unauthenticated | `/health`, `/ready` (trivial). `POST /webhooks/clerk` (the HMAC is checked before any DB work). `GET /ws` (with §6, unauthenticated sockets time out after 10 s; with the PEM, verification is CPU-only). | Large bodies. | **Body-size limit only** |
| Expensive | `GET /search` (loads the ±4 h candidate window, scores in Python). `/admin/analytics` (admin-only). Lists are capped at `limit≤100`. | Low at launch volumes. | Later: per-user on `/search` |
| Side effects on other users | `POST /rides/{id}/requests`: creating, cancelling and re-creating a request in a loop pushes notifications to the driver (no email: only welcome, approve and reject send email). `POST /rides`: listing spam pollutes search. | Requires a verified Clerk account. The admin can deactivate the abuser, which takes effect on the next request and closes their sockets. | Later: per-user write limits |
| Normal authenticated | Every other GET and PATCH. | None worth limiting. | No |

**App-level vs host-level for this architecture.**
- **Host-level:** none of Render, Railway or Fly offers configurable per-IP request rate limiting on the app proxy (Fly has only per-machine concurrency limits). Doing it at the edge means putting Cloudflare's proxy in front: free tier, a limited number of rules, WebSockets supported. That only works **per IP**, which misfires behind mobile carrier NAT, and it can't see user identity.
- **App-level:** a ~40-line Redis fixed-window limiter keyed by **user id** on 3–4 routes. It's precise and testable. Redis is already provisioned, and the limiter fails open if Redis is down. It does change API behaviour (below).

**Recommendation:**
- **Before launch:** a **64 KB request body limit** as a tiny ASGI middleware. The largest legitimate body is under 2 KB, the webhook included, and the middleware works on every host. Plus `--ws-max-size 65536` (§4).
- **After launch:** app-level per-user limits on `POST /rides/{id}/requests` (e.g. 20/h), `POST /rides` (10/h) and `GET /search` (60/min). Turn them on when monitoring shows abuse or before any marketing push. Admin deactivation is the launch-time control.

**Contract changes, if implemented:**
- Body limit: **413 `PAYLOAD_TOO_LARGE`** with the standard envelope. Add it to §5 and to openapi as a global response.
- Rate limiting (later): **429 `RATE_LIMITED`** with a `Retry-After` header on the limited operations, plus a `messageFor` entry on the frontend.

**Test.**
- Body limit: a 65 KB POST gets 413 with the envelope (contract helper), and normal bodies pass. A chunked body without `Content-Length` is also cut off.
- Rate limit (later): the N+1th call gets 429 with `Retry-After`, a different user isn't affected, and the call is allowed when Redis is down.

**When.** Body and frame limits: **recommended** before production. Per-user rate limits: **can wait**.

---

## 10. Error monitoring

| Option | What you get | Gaps | Cost and effort |
|---|---|---|---|
| Structured logs only (already JSON, with request ids) | A full record in the host's log viewer | No alerting: you find out only if you look. Host log retention is short (days, plan-dependent). **Browser errors are invisible.** | Zero |
| Sentry only | Grouped exceptions, email alerts on new issues, stack traces, browser errors | Not a log of normal activity | Free tier for 1 user; about 1 h to wire |
| **Minimal combination** | Logs stay the record. Sentry is errors-only: backend `sentry-sdk[fastapi]` (our `_unhandled` handler uses `logger.exception`, which Sentry's logging integration captures) and frontend `@sentry/react` wired into the existing `ErrorBoundary`. `send_default_pii=False`, **no tracing, no session replay.** Plus a free uptime monitor on `/ready` with email alerts. | Sentry becomes a data processor to list in the privacy policy | Free; small |

**Recommendation:** the minimal combination. It's proportional: it answers "how will I know it broke?" for both server and browser, with no paid tier. Configure it with `SENTRY_DSN` (backend) and `VITE_SENTRY_DSN` (frontend). An empty DSN disables it, so dev and test are unaffected.

**Affects.** Backend and frontend (init only), deployment env, and the privacy policy. No contract or DB change.

**Test.** An empty DSN means no init (unit test). After deploy, trigger one deliberate test error from each side and confirm the alert email arrives.

**When.** **Recommended** before production (decision D2).

---

## 11. Other deployment risks (short form)

| # | Current → risk | Fix | Affects | Test | When |
|---|---|---|---|---|---|
| 11.1 | No Dockerfile, host config or production start command → can't deploy | `backend/Dockerfile`: multi-stage `python:3.12-slim` + uv, `uv sync --frozen --no-dev`, non-root user, `HEALTHCHECK` on `/health`, the CMD from §4. `.dockerignore`. Host config file per D1. | Deploy | `docker build` and run locally against compose Postgres and Redis; `/ready` returns 200 | **Must** |
| 11.2 | CI is blocked → no automated gate before deploy | `scripts/check-all.sh` (backend ruff/format/import, frontend typecheck/lint/test/build, migration tests, a pytest subset) run before every push. Add the frontend job and backend format check to `ci.yml` for when Actions works. The host auto-deploys `main`. | Scripts, CI | Run the script | **Recommended** |
| 11.3 | `/docs` (Swagger) is public in production | `docs_url=None` when production | Backend | Prod settings → `/docs` returns 404 | **Recommended** |
| 11.4 | JWKS refetch on an unknown `kid` runs under a global lock → forged tokens stall auth | Moot in production once the PEM is required (§3.1). Later: lock-free cache hit plus at most one refetch per 60 s | Backend | Concurrency unit test | **Can wait** (PEM covers it) |
| 11.5 | `app.seed` writes to whatever `DATABASE_URL` points at | Refuse when `APP_ENV=production` | Backend | Unit test | **Recommended** |
| 11.6 | `env.ts` falls back to `localhost` when `VITE_*` are missing → a production bundle silently points nowhere | In `import.meta.env.PROD`, missing URLs render the existing `ConfigurationNeeded` screen | Frontend | Vitest with the env stubbed | **Recommended** |
| 11.7 | The MSW chunk (447 KB) and `mockServiceWorker.js` ship in `dist/` (inert) | Gate `startMocks` on `DEV \|\| MODE==='mock'` so it tree-shakes. Copy the worker only in mock mode. | Frontend | `dist/` has no `browser-*.js` or worker | **Recommended** |
| 11.8 | No security headers on the SPA. Google Fonts loads from Google (sends user IPs to Google; a GDPR concern). | Static host headers: CSP (self, Clerk FAPI, `api.mapbox.com`, API https/wss origin), HSTS, `nosniff`, `Referrer-Policy`, `frame-ancestors 'none'`. Self-host the Archivo font. | Frontend, deploy | Check headers on the deployed URL; no console CSP errors through the E2E flow | **Recommended** |
| 11.9 | Default DB pool (5+10), no statement timeout | `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` settings (keep under the managed DB's connection cap), `command_timeout=30` | Backend, config | Import plus the suite | **Recommended** |
| 11.10 | Mapbox token unrestricted, no billing card | Restrict the token to `https://app.<domain>`. Add billing or accept the free-tier cap (the autocomplete error state exists). | Mapbox dashboard | Autocomplete works on prod; fails from other origins | **Must** (restriction) |

---

## 12. Personal data inventory and legal pages (B-4)

**What's stored** (`contracts/schema.sql`, the models):

| Data | Where stored | Collected in | Who can see it | Why it's needed |
|---|---|---|---|---|
| Email | `users.email` (mirror of Clerk) | Clerk sign-up | Self, admins | Account identity, email notifications |
| Name | `users.name` | `OnboardingScreen`, `ProfileScreen` | **Everyone** (public profile) | Shown to ride partners |
| **Date of birth** (required) | `users.date_of_birth` NOT NULL | `OnboardingScreen` | Self, admins | 18+ check (backend-enforced). **Stored permanently, though only needed once.** |
| **Gender** (optional) | `users.gender` | `OnboardingScreen`, `ProfileScreen` | Self, admins. Used for `gender_only` ride filtering, not shown publicly. | Matching filter |
| **Phone** (optional) | `users.phone` | `OnboardingScreen`, `ProfileScreen` | Self and **admins only** (`AdminUserDetailScreen`). **Never shown to ride partners or used by any feature.** | Nothing today (see D3) |
| Vehicle make, model, colour | `users.vehicle` jsonb | `OnboardingScreen`, `VehicleEditor` | Everyone | Ride identification |
| **Licence plate** | `users.vehicle.plate` | same | Driver, approved passengers, admins | Pick-up identification |
| Preferences (smoking, pets, language, notification toggles) | `users.preferences` | Onboarding, Profile | Self (ride prefs public on rides) | Matching |
| Terms acceptance time | `users.terms_accepted_at` | Onboarding checkbox | Admins | Consent record (no document version stored) |
| Activity | `users.last_login_at`, created/updated | Automatic | Admins | Analytics |
| **Precise locations and addresses** (possibly home or work) | `rides.start/end_address`, `_lat/_lng` | `CreateRideScreen`/`EditRideScreen` (Mapbox) | Everyone who can see the ride | Matching |
| Search queries | **not stored** (sent to the API, not persisted) | `SearchScreen` | — | — |
| Ride free-text notes | `rides.notes` | Ride form | Ride viewers | — |
| Trips and requests | `ride_requests` | Request flow | Driver and passenger | Core feature |
| Ratings, free-text comments, tags (about another person) | `ratings` | `RateScreen` | Ratee profile / viewers | Reputation |
| Notification texts (contain full addresses and times) | `notifications` | Generated | Recipient | Feed |
| Webhook ids | `clerk_webhook_events` (id, type, time; **no payload**) | Clerk | — | Idempotency |

**Third parties receiving personal data:**
- Clerk: identity, credentials, IP/device.
- Mapbox: address search text and the user's IP, from the browser.
- SMTP provider: email, name, ride addresses and times in the message body.
- Google Fonts: IP, until it's self-hosted.
- The hosting provider: everything.
- Sentry, if chosen: error context.

**Gaps:**
- **There is no account deletion.** Clerk `user.deleted` only sets `is_active=false` (`webhooks/service.py:_deactivate`), and all PII is kept forever.
- No privacy contact.
- No document version tied to the consent.

**What must exist before launch (engineering and product, not legal text):**
1. **Terms of Service** and **Privacy Policy** documents, provided by you. Each has an effective date.
2. Public routes `/terms` and `/privacy` that need no login, linked from:
   - the Welcome screen;
   - the onboarding checkbox label (as real links);
   - the Profile screen (footer).
3. **Account deletion that actually removes personal data.** On Clerk `user.deleted`, and through an admin CLI for emailed requests, anonymise the user:
   - name → "Deleted user";
   - email → `deleted-<id>@deleted.invalid`;
   - `clerk_user_id` → `deleted_<id>`;
   - phone, gender and vehicle → null;
   - DOB → a fixed sentinel (the column is NOT NULL);
   - preferences → null;
   - `is_active` → false.

   Rides, requests and ratings stay, for the other party's history. **No schema change is needed.**

   *Affects:* backend (webhook and CLI) and contract §4 wording.

   *Test:* after a `user.deleted` webhook, the row holds none of the original values, the public profile shows "Deleted user", and a replay is a no-op.
4. A privacy contact address, shown in the policy and on the Profile screen.
5. The facts in the inventory above, handed to whoever writes the policy, including retention of logs (host-dependent days) and backups (provider-dependent days).
6. Self-hosted font (11.8), so no IP goes to Google without consent.

**When.** Items 1–4: **must**. Item 6: recommended. Storing a `terms_version` with the consent and a "delete my account" button in Profile: **can wait** (deleting the Clerk account through Clerk's `<UserProfile/>` already triggers the webhook).

---

## 13. Hosting comparison (no ranking)

All three meet the hard requirements: FastAPI in a container or native runtime, WebSockets, custom domains with automatic TLS, env-var secrets, GitHub push-to-deploy or a CLI. **Verify current pricing and plan limits before choosing.**

| Requirement | Render | Railway | Fly.io |
|---|---|---|---|
| Python / FastAPI | Native Python runtime or Dockerfile | Auto-detect (Railpack) or Dockerfile | Dockerfile (Fly runs images as VMs) |
| PostgreSQL | **Managed** Render Postgres. Backups and PITR on paid tiers. The free DB expires, so it's unusable for production. | One-click Postgres **service** (a container with a volume). Backups via volume backups, less managed than the other two. | **Fly Managed Postgres** (newer offering, with backups and HA; check region availability), or legacy self-operated Fly Postgres |
| Redis | Managed **Key Value** (Redis-compatible) | One-click Redis service (container) | **Upstash Redis** via `fly redis create` (managed, TLS) |
| WebSockets | Yes | Yes | Yes |
| Always-on single process | Paid instance types don't sleep (the free tier sleeps after idle, which breaks jobs and WS). Instance count is set explicitly. | Always on by default. "Serverless / sleep" must stay off. | Set `auto_stop_machines="off"` and `min_machines_running=1`. Fly recommends ≥2 machines, but a single machine has **no automatic failover if its host fails**. |
| In-process jobs | Fine (always-on) | Fine | Fine with auto-stop off |
| Env and secrets | Dashboard, env groups, `render.yaml` (`sync:false` keeps secrets out of git) | Per-service variables. **Reference variables** (`${{Postgres.DATABASE_URL}}`) wire services together. | `fly secrets set` (CLI, encrypted) |
| Custom domain and HTTPS | Yes, automatic certs (web service and static site) | Yes, automatic | `fly certs add`, automatic |
| Health checks | **One** `healthCheckPath`, used for deploy gating **and** ongoing monitoring (failing instances are pulled and restarted) | Healthcheck path used **only at deploy time**; ongoing it only restarts on crash. You need an external uptime monitor. | Most flexible: service checks (routing) and machine checks, so liveness and readiness can be fully separate |
| Migrations | Pre-deploy command (paid instances) | Pre-deploy command | `release_command` in a temporary machine |
| Frontend (static SPA) | **Static Sites product**: free, CDN, SPA rewrite rules and **custom headers** configured natively | No static product. Serve `dist/` from a small container (e.g. Caddy) and write the SPA rewrite and headers yourself, or host the frontend elsewhere. | No static product: same as Railway (container or an external static host) |
| Deploys with Actions blocked | GitHub integration auto-deploys on push to `main` (no Actions needed) | GitHub integration auto-deploys on push (no Actions needed) | Normally `fly deploy` from your machine or GitHub Actions. With Actions blocked, **deploys are manual CLI runs** (check whether Fly's dashboard GitHub integration meets your needs). |
| Logs | Dashboard stream, retention by plan, log streams to external services | Dashboard, retention by plan | `fly logs` (live). Retention needs a log shipper. |
| One-off shell (admin CLI, §3.2) | Shell on paid instances, or one-off jobs | `railway ssh` / `railway run` | `fly ssh console` |
| Scale later | Instance count and autoscaling on paid plans | Replicas setting | Easiest multi-region and multi-machine |
| Cost model | Fixed per service tier: predictable | Usage-based (CPU/RAM/egress) on top of a plan minimum: cheap at low load, less predictable | Per machine plus add-ons; Upstash billed separately |
| Ops complexity for *this* app | Lowest: four resources in one dashboard and one blueprint file | Low for the backend; frontend serving and DB backups are on you | Highest: Docker, the fly.toml machine model, CLI deploys, separate Redis vendor |

The app's code is host-agnostic. Only one config file (`render.yaml`, `railway.json` or `fly.toml`) and the frontend serving differ.

---

## 14. Deployment architecture proposal

```
                         ┌──────────────── Clerk (prod instance, clerk.<domain>) ─────────────┐
                         │  sign-in/up UI, sessions, JWT signing          webhooks (Svix) ─┐ │
                         └──────────▲──────────────────────────────────────────────────────┼─┘
                                    │ Clerk JS                                             │
 Browser ── HTTPS ──► app.<domain>  (static host/CDN: React dist/, SPA rewrite, CSP/HSTS)  │
    │                                                                                      │
    │  REST  https://api.<domain>/api/v1/…   Authorization: Bearer <Clerk JWT>             │
    │  WS    wss://api.<domain>/api/v1/ws    first message {"event":"auth",…}              │
    │  Mapbox geocoding (browser → api.mapbox.com, token restricted to app.<domain>)       │
    ▼                                                                                      ▼
 Host edge / TLS termination  ───────────────────────────────────────►  api.<domain>
    ▼
 FastAPI container: uvicorn app.main:app  (1 instance × 1 process, never sleeps)
    • REST + WebSocket registry (in memory) + jobs loop (pg advisory lock per pass)
    • JWT verified offline with CLERK_JWT_KEY (no Clerk call per request)
    ├──► PostgreSQL 16 (managed, private network, TLS, daily backups/PITR)
    ├──► Redis (managed; WS presence counters; later rate limits) — optional for function
    ├──► SMTP provider (after commit, background task, 10 s timeout)
    ├──► Clerk Backend API (admin ban/unban, 5 s timeout, best effort)
    └──► Sentry (errors only)                       Uptime monitor ──► GET /api/v1/ready
```

**Where each component runs.**
- The frontend runs as static files on the host's static product (Render), or on a static host or a small Caddy container (Railway/Fly).
- The backend runs as one always-on container or service.
- Postgres and Redis are the host's managed offerings in the same region, on the private network.
- Clerk, Mapbox, SMTP and Sentry are SaaS.

Subdomains (`app.` and `api.`) are simpler than one origin with path routing. CORS and `azp` are already built for this.

**Environment variables.**
- **Backend:** runtime env from the host's secret store. No `.env` file in production; `Settings` reads the process env, and the repo `.env` is simply absent. The production validator (§3.1) guarantees completeness at boot.
- **Frontend:** the `VITE_*` values are **build-time** variables in the static build settings and are baked into the bundle. They're public by design: the publishable key, the Mapbox public token and the URLs. No server secret has a `VITE_` prefix.
- `.env.example` gets a "Production" section listing both sets.

**How deploys happen.**
1. You run `scripts/check-all.sh` locally, then push `main`.
2. The host builds the backend image and the frontend bundle.
3. **Pre-deploy / release:** `alembic upgrade head`. If it fails, the deploy aborts and the old version keeps serving.
4. The new container starts, and the host polls `/ready` until it returns 200.
5. Traffic switches, and the old container gets SIGTERM. Its sockets close and clients reconnect to the new one; the advisory lock prevents a doubled job pass.

On Fly, steps 2–5 run when you invoke `fly deploy`.

**How migrations happen.** Only through the release step. Never run manual DDL against production. Migrations are expand/contract (§5). Take a backup before destructive changes. Roll forward, never downgrade.

**Health checks.** `/health` is liveness (container or machine), `/ready` is readiness (host deploy gating, plus the uptime monitor). See §7 for Render's single-path caveat.

**Logs and errors.**
- JSON logs to stdout, with `request_id` and an access line per request. The host captures them, with no tokens and no email addresses (§6, §8).
- Sentry alerts by email on new backend or frontend errors.
- The uptime monitor alerts on `/ready` failing.

**Single-worker limitation.** Enforced by the start command (no `--workers`), a host instance count of 1 with autoscaling off, sleep disabled, the advisory lock for deploy overlap, and the README. The scale-out path is in §4.

---

## 15. Must Fix Before Production

| # | Item | Section | Contract change |
|---|---|---|---|
| M1 | Production settings validator (Clerk, CORS, DB/Redis, SMTP), DB URL normalisation, PEM required | §3.1 | — |
| M2 | Admin: no auto-promotion in production, `admin_cli grant/revoke` | §3.2 | §4 wording |
| M3 | Clerk production instance configured as in §3.3 (you) | §3.3 | — |
| M4 | Single process pinned. Advisory lock on job passes. Uvicorn flags. | §4 | — |
| M5 | Alembic builds the test DB, plus migration tests (upgrade, single head, round trip, check, parity, non-superuser) | §5 | CLAUDE.md/CONTRACT wording |
| M6 | WS first-message auth plus an Origin check | §6 | §6 (breaking) |
| M7 | `/health` liveness and `/ready` readiness | §7 | `/health` shape (breaking), `/ready`, `NOT_READY` |
| M8 | SMTP timeout, 465 support, send after commit, no addresses in logs | §8 | — |
| M9 | Dockerfile, `.dockerignore`, host config, release-step migration | §11.1, §14 | — |
| M10 | Legal pages and links, a privacy contact, anonymise on `user.deleted` plus a CLI | §12 | §4 wording |
| M11 | Mapbox token restricted to the production domain | §11.10 | — |

All the contract changes (M2, M6, M7, M10, plus 413 from R1) go in **one** bump to **0.5.0**, committed alone, with `gen:api`, the MSW mocks and the tests updated in the same chunk.

## 16. Recommended Before Production

| # | Item | Section |
|---|---|---|
| R1 | 64 KB body limit (413 `PAYLOAD_TOO_LARGE`), WS frame cap | §9 |
| R2 | Sentry errors-only (backend and frontend), uptime monitor on `/ready` | §10 |
| R3 | `scripts/check-all.sh`; frontend job and format check in `ci.yml` | §11.2 |
| R4 | `/docs` off in production; seed guard | §11.3, §11.5 |
| R5 | Frontend env guard; mocks out of `dist/` | §11.6–7 |
| R6 | Security headers; self-hosted font | §11.8 |
| R7 | DB pool and timeout settings | §11.9 |

## 17. Can Wait Until After Launch

- Per-user rate limits (429) on request creation, ride creation and search (§9).
- Redis pub/sub fan-out, a separate worker process, TTL presence counters: only when there's more than 1 instance (§4).
- A durable email outbox with retries (§8).
- JWKS lock-free cache (§11.4; not used once the PEM is set).
- Readiness checks the Alembic revision (§7).
- `terms_version` column, an in-app "delete account" button (§12).
- A search SQL bounding-box prefilter, route code splitting, `fetch` timeouts, Svix timestamp tolerance, stopping the WS reconnect loop for onboarding-required users, notification retention, phone-format tightening (already deferred by you).

## 18. Decisions I Need From You

Everything else above is derived from the requirements and will be implemented as written once you approve.

1. **D1: Host.** Render, Railway or Fly.io (§13). This determines the config file, how the frontend is served, and whether deploys are push-based or CLI.
2. **D2: Sentry.** Yes or no for errors-only monitoring (§10). If yes, it must be listed in the privacy policy.
3. **D3: Phone number.** It's collected but never shown to ride partners or used. Keep it as is (optional, admin-visible), or stop collecting it? The privacy policy depends on the answer, and so does data minimisation.

**Things only you can do** (not decisions, but they block launch):
- the domain;
- the Clerk production instance (§3.3);
- a transactional email provider account plus SPF/DKIM/DMARC on the sending domain (any SMTP provider works; only the `SMTP_*` vars change);
- the ToS and Privacy Policy text;
- Mapbox token restriction and billing;
- the host account and payment;
- after the first deploy, signing up, onboarding, and running `admin_cli grant <your email>`.

## 19. Proposed implementation order

Each step is one chunk: it gets its checks and a commit, and stops for your review.

1. **Contract 0.5.0** (M2, M6, M7, M10 wording, plus 413). A contract-only commit.
2. **Config and auth:** M1, M2 (CLI and guard), R4, R7.
3. **Reliability:** M4 (advisory lock), M7 (health/ready), M8 (SMTP), R1 (body limit).
4. **WebSocket auth:** M6, backend and frontend together.
5. **Migrations:** M5, then a full pytest run in the background.
6. **Privacy:** M10 (anonymisation, CLI, legal routes and links; placeholder text until yours arrives), R6 (font).
7. **Frontend production hygiene:** R5, R2 (Sentry, if D2 is yes).
8. **Build:** M9 (Dockerfile), R3 (check-all script and CI).
9. **Hosting** (needs D1): host config, R6 headers, deploy runbook.
10. **Production** (you lead): M3, M11, DNS, deploy, then the post-deploy checklist below.

**Post-deploy checklist:**
- [ ] `/health` returns 200. `/ready` returns `{"status":"ready","db":true,"redis":true}`. `/docs` returns 404.
- [ ] Response headers on `app.<domain>` include CSP, HSTS and nosniff. Browser console has no CSP errors.
- [ ] Sign up and onboard, run `admin_cli grant`, and see the admin panel. A second account doesn't see it.
- [ ] Full flow on two devices: post, request, approve (the live push arrives), start, complete, both rate.
- [ ] A real email arrives (welcome / approved) and isn't in spam.
- [ ] Logs are JSON, contain no `token`, no `eyJ` and no email addresses. A reminder fires for a ride 59 minutes out.
- [ ] Clerk webhook test returns 204. Deleting a test Clerk user anonymises their row. Banning in admin gives 403 on their next call.
- [ ] A backup exists; restore it once into a scratch DB.
- [ ] A Sentry test error from the backend and frontend reaches you (if D2). The uptime monitor is green.
