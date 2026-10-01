# RideMatch test suite

Contract tests for the backend. They are written from `contracts/` — `openapi.yaml`
for shapes, `CONTRACT.md` for behaviour, `schema.sql` for the database — and never
from the backend source, so that a backend that misreads the contract fails here.

## Running

```bash
docker compose up -d          # from ridematch-platform/ — Postgres + Redis
cd tests
uv sync
uv run pytest -q
```

Checks before committing:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

## Layout

| Path | What it holds |
|---|---|
| `conftest.py` | Pins the backend's environment **before** it is imported, then the fixtures |
| `support/env.py` | The test environment: `APP_ENV=test`, test DB, `JOBS_ENABLED=false`, `EMAIL_BACKEND=memory`, Clerk test values |
| `support/keys.py` | RSA key pair, Clerk-style token signer, and deliberately forged tokens |
| `support/db.py` | The test database, built from `contracts/schema.sql`, truncated per test |
| `support/contract.py` | Validates a response against `openapi.yaml` |
| `support/assertions.py` | `expect_status` / `expect_error` — every API assertion goes through these |
| `support/factories.py` | Users, created through the API the way the contract says they are |
| `unit/` | The harness itself, plus `schema.sql`. No backend needed |
| `api/` | One file per area |
| `e2e/` | Playwright (Phase 7) |

## How a test asserts

`expect_status` and `expect_error` check the status code, validate the body against
the matching `openapi.yaml` schema, and — for errors — check the stable `code`.
Using them is what makes docs/roles/tests.md's "every API test checks all three"
true by construction.

Two deliberate strictnesses:

- **An undocumented status is a failure.** A 500 where the contract lists 401/403/404
  fails with a message naming the documented statuses.
- **Responses are closed.** Any object schema that lists `properties` and says nothing
  about `additionalProperties` is validated as if it said `additionalProperties: false`,
  so an undeclared field — a plate or an email leaking into `UserPublic` — fails.
  Pass `strict=False` to opt out of this for one call.

## Authentication

Tests never call Clerk (CONTRACT.md D13). `conftest.py` generates an RSA key pair,
hands the public half to the backend as `CLERK_JWT_KEY`, and signs tokens with the
private half using the same claims Clerk sends. The backend has no test-only bypass;
only the key differs.

```python
user = await users.create()  # onboarded, no vehicle
driver = await users.create_driver()  # onboarded, with a vehicle
admin = await users.create_admin()
headers = user.headers  # fresh token
headers = user.headers_with(expires_in=-3600)  # an expired one
headers = users.stranger_headers()  # valid token, no profile
```

## Database

The schema comes from `contracts/schema.sql`, which that file invites tests to load
directly. Running the contract rather than the backend's Alembic migration is the
point: a migration that drifts from the contract shows up as failing tests.

Every table is truncated before each test. `support/env.py` refuses to start if
`TEST_DATABASE_URL` does not name a database with "test" in it.

## Open item

`pyproject.toml` does not yet depend on `../backend`: `uv lock` fails while that
directory has no `pyproject.toml`. The dependency and its `[tool.uv.sources]` entry
are in the file, commented, with the reason. Uncomment both and run `uv sync` as soon
as @backend lands the `ridematch-backend` package; until then the `api/` tests skip
with an explanatory message and CI skips them too.

If the app does not live at one of the import paths in `support/app.py`, set
`RIDEMATCH_APP=module:attr`.
