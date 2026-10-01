# RideMatch: build plan

Phases run one at a time. Inside a phase, the three sessions work in parallel.
A phase is **done** only when its gate passes. Then Dvir merges into `main` and starts the next phase.

**Merge order at each gate:** `feat/backend` → `feat/tests` → `feat/frontend` into `main`. Then every session runs `git merge main`.

---

## Phase 0: Setup (Dvir, ~30 min)
1. Extract into `C:\Users\dvir5\Projects\ridematch-platform` (the repo root), `git init`, first commit on `main`.
2. Clerk: create the app. Require a verified email. Enable Google login (optional). Add the custom session-token claim `{"email": "{{user.primary_email_address}}"}`. Copy the keys.
3. Mapbox: create an account and a public token.
4. `cp .env.example .env` and fill it in. `docker compose up -d`.
5. `./scripts/setup-worktrees.sh` (in Git Bash), then open 3 PowerShell tabs with the commands it prints.

**Gate:** in each session, `/list-agents` shows the other two.

---

## Phase 1: Foundations
**@backend**
- `backend/` as an installable uv package `ridematch-backend` exposing `app` (so tests can import it).
- Config (pydantic-settings), DB session, SQLAlchemy models + first Alembic migration matching `schema.sql` exactly.
- The error envelope `{code, message, details}` for all errors, including 422 validation.
- Clerk auth dependency (CONTRACT §2): JWKS or `CLERK_JWT_KEY`; checks `iss`/`azp`/`exp`; user lookup; `ONBOARDING_REQUIRED` / `ACCOUNT_DEACTIVATED`.
- Endpoints: `GET /health`, `POST /users/me/onboarding`, `GET/PATCH /users/me` (incl. vehicle), `GET /users/{id}`.

**@frontend**
- Vite + TS scaffold, Tailwind, router, TanStack Query, `envDir: '..'`.
- Typed API client generated from `contracts/openapi.yaml` (`openapi-typescript`). Attach the Clerk token to every call. Handle errors by `code`.
- MSW mocks built from the contract, switchable with an env flag.
- Screens: Welcome, Sign In/Up (Clerk components), Onboarding (incl. optional vehicle), Role Selection. App shell with the role switcher and bottom navs (empty tabs).

**@tests**
- `tests/` uv project that depends on `../backend` (path dependency).
- Fixtures: fresh `ridematch_test` DB per session with a transaction/truncate per test; RSA key pair + token signer (`CLERK_JWT_KEY`); factories for users, onboarded users, admins, vehicles.
- A helper that validates every response body against the matching `openapi.yaml` schema. Use it in every test.
- Tests: auth (missing/expired/wrong-`azp`/wrong-`iss` token), onboarding (18+, ToS, twice, admin seed only when no admin exists), `/users/me`, vehicle validation.
- `.github/workflows/ci.yml`: Postgres + Redis services, backend lint, full test suite.

**Gate:** tests green. A real sign-up in the browser reaches Role Selection against the real backend.

---

## Phase 2: Core ride loop (rides + requests)
**@backend**: rides create/list-mine/get/patch/cancel/start/complete; requests create/list/incoming/mine/get/approve/reject/cancel. All rules in CONTRACT §3–§4, with the row lock on approve, the 1h cancel cutoff and `PREVIOUSLY_REJECTED`. Write notification rows (no push yet).
**@frontend**: driver (Create/Edit Ride with Mapbox address autocomplete, My Rides, Ride Details, Requests tab with approve/reject) and passenger (Ride Details, Request, My Trips, cancel), with every 409 shown as a clear message.
**@tests**: full state machines (every allowed and forbidden transition), seat arithmetic, the approve race on the last seat (two concurrent approvals → one 200, one 409), the edit-lock rules, the cutoffs, plate visibility, permissions (someone else's ride → 403).
**Gate:** tests green. In the browser, a driver creates a ride, a passenger requests it, the driver approves, and the passenger sees it in My Trips.

## Phase 3: Search & matching
**@backend**: `/search` exactly as in CONTRACT §7 (candidate filters, formulas, sort, pagination).
**@frontend**: the Search screen (inputs with autocomplete, results with the match badge, sort, filters).
**@tests**: exact score numbers for hand-computed cases (each component, boundaries such as Δ=2h and 4h, radius edge, budget 0), exclusions (own ride, already requested, gender_only, full), sort orders.
**Gate:** tests green. A search in the browser finds the ride from Phase 2.

## Phase 4: Real-time notifications & background jobs
**@backend**: WebSocket (§6) with the Redis registry; push after commit; the email service (console/smtp/memory); in-process jobs (1h reminder, auto-complete, stale-cancel) taking `now`; the notification endpoints.
**@frontend**: WS client with token refresh and reconnect with backoff; Notifications tab (read/read-all/clear); badges; live updates to lists.
**@tests**: WS auth close codes (4401/4403), ping/pong, the push payload equals the REST object; every row of the trigger table in §7 (who gets what, which ones email) using the memory outbox; jobs run with a fixed `now`.
**Gate:** tests green. Two browsers: approving in one shows up live in the other.

## Phase 5: Ratings & stats
**@backend**: ratings create/pending/list, the cached-average update, `/users/me/stats`.
**@frontend**: post-ride rating prompt, Rating screen, public profiles with ratings, Home stats, Profile trip stats.
**@tests**: participant/direction rules, duplicate rating, the average math, stats counters.
**Gate:** tests green. Complete a ride, both sides rate, and the averages update.

## Phase 6: Admin + Clerk webhook
**@backend**: `/admin/*` (with Clerk ban/unban), analytics, `/webhooks/clerk` (Svix verify, idempotency table, `user.updated`/`user.deleted`).
**@frontend**: the Admin panel (User Management, Ride Monitoring, Analytics). It's visible only when `is_admin`.
**@tests**: every admin endpoint as non-admin → 403; deactivate/reactivate effects (403 on the next request, sockets closed); force-cancel side effects; analytics numbers on seeded data; webhook signatures (valid, invalid, replayed `svix-id`).
**Gate:** tests green. Dvir tests the admin panel by hand.

## Phase 7: Hardening & end-to-end
**@backend**: a seed script with demo data, structured logging, rate limiting on writes (optional), query/index check on search.
**@frontend**: loading, empty and error states everywhere; mobile layout; basic accessibility; a production build with no warnings.
**@tests**: Playwright E2E for the main flows against the full stack (Clerk dev instance test users); Schemathesis fuzzing of the API against `openapi.yaml`; fix flaky tests.
**Gate:** E2E + fuzzing green in CI.

## Phase 8: Deploy (Dvir + @backend)
- Pick hosting (e.g. Render, Fly or Railway, with managed Postgres + Redis). Dockerfile for the backend; the frontend as static files.
- Domain + HTTPS. Clerk production instance with its own keys. Add the domain to `CLERK_AUTHORIZED_PARTIES`, `CORS_ORIGINS` and the Mapbox token restrictions.
- Set the Clerk webhook to `https://<api-domain>/api/v1/webhooks/clerk`.
- CI deploys `main` after tests pass.

## Finish
When all branches are merged: `./scripts/remove-worktrees.sh`. Only `ridematch-platform\` remains: the whole project on `main`.
