"""Session wiring for the RideMatch contract tests.

Order matters at the top of this file: `support.env.apply()` has to run before
the backend package is imported anywhere, because pydantic-settings reads the
environment at import time. Keeping it at module level guarantees that - pytest
imports conftest.py before it imports any test module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import env as test_env
from support.contract import ContractValidator, validator
from support.db import TestDatabase
from support.factories import Users
from support.keys import KeyPair, TokenSigner
from support.rides import RideRequests, Rides
from support.search import Search

# One key pair per session: the public half is what the backend verifies with.
KEYS = KeyPair.generate()
test_env.apply(KEYS.public_pem)

# Set RIDEMATCH_REQUIRE_BACKEND=1 (CI does, once backend/ exists) to turn a
# missing backend package into a hard failure instead of a skip.
REQUIRE_BACKEND = os.environ.get("RIDEMATCH_REQUIRE_BACKEND") == "1"


# ── keys, signer, contract ──────────────────────────────────────────────
@pytest.fixture(scope="session")
def keys() -> KeyPair:
    return KEYS


@pytest.fixture(scope="session")
def other_keys() -> KeyPair:
    """A second key pair, for tokens signed by the wrong issuer key."""
    return KeyPair.generate()


@pytest.fixture(scope="session")
def signer(keys: KeyPair) -> TokenSigner:
    return TokenSigner(keys.private_pem)


@pytest.fixture(scope="session")
def contract() -> ContractValidator:
    return validator()


# ── database ────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
async def database() -> TestDatabase:
    """A database built from contracts/schema.sql, fresh for the session."""
    db = TestDatabase()
    try:
        await db.reset_schema()
    except OSError as exc:  # pragma: no cover - environment problem, not a test failure
        pytest.skip(
            f"Cannot reach the test database at {db.dsn}: {exc}. "
            "Is `docker compose up -d` running in ridematch-platform?"
        )
    return db


@pytest.fixture
async def db(database: TestDatabase) -> TestDatabase:
    """Truncate before each test, so a failing test cannot poison the next one."""
    await database.truncate_all()
    return database


# ── the application under test ──────────────────────────────────────────
@pytest.fixture(scope="session")
def backend_app():
    from support.app import BackendNotInstalled, load_app

    try:
        return load_app()
    except BackendNotInstalled as exc:
        if REQUIRE_BACKEND:
            pytest.fail(str(exc), pytrace=False)
        pytest.skip(f"backend not installed yet - {exc}")


@pytest.fixture(scope="session")
async def app(backend_app, database: TestDatabase):
    """Run the app's lifespan once the schema exists."""
    from asgi_lifespan import LifespanManager

    async with LifespanManager(backend_app) as manager:
        yield manager.app


@pytest.fixture
async def client(app, db: TestDatabase):
    """In-process ASGI client, already rooted at the API prefix."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://testserver{test_env.API_PREFIX}",
    ) as http_client:
        yield http_client


@pytest.fixture
async def root_client(app, db: TestDatabase):
    """Client without the API prefix, for paths outside it."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
def users(client, signer: TokenSigner, db: TestDatabase) -> Users:
    return Users(client, signer, db)


@pytest.fixture
def rides(client, users: Users) -> Rides:
    return Rides(client, users)


@pytest.fixture
def requests(client, users: Users) -> RideRequests:
    """The ride-request endpoints. Named for the contract's resource, not for
    any HTTP library - the suite only ever speaks through `client`."""
    return RideRequests(client, users)


@pytest.fixture
def search(client) -> Search:
    return Search(client)


@pytest.fixture
async def second_client(app, db: TestDatabase):
    """A second in-process client, for the concurrent-approval race.

    Two clients make it unambiguous that the two calls travel as two separate
    requests, each with its own backend session and therefore its own
    transaction - which is the whole point of the `SELECT … FOR UPDATE` in
    CONTRACT.md §4.
    """
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://testserver{test_env.API_PREFIX}",
    ) as http_client:
        yield http_client


# ── convenience ─────────────────────────────────────────────────────────
@pytest.fixture
async def user(users: Users):
    """One ordinary onboarded user."""
    return await users.create()


@pytest.fixture
async def driver(users: Users):
    """An onboarded user with a vehicle."""
    return await users.create_driver()


@pytest.fixture
async def passenger(users: Users):
    """An onboarded user with no vehicle: they can only ride along."""
    return await users.create()


@pytest.fixture
async def other_user(users: Users):
    """Someone with no connection to the ride under test."""
    return await users.create()


@pytest.fixture
async def admin(users: Users):
    return await users.create_admin()


@pytest.fixture
async def offer(rides: Rides, driver):
    """One ride, departing far enough ahead that it is editable and not yet
    startable (CONTRACT.md §3: start is allowed from departure - 2h)."""
    return await rides.offer(driver)
