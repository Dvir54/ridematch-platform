"""Alembic is the database's source of truth (plan §5); `contracts/schema.sql` is its reference.

Each test gets a scratch database of its own, so nothing here touches the suite's test DB.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest

from support import env
from support.migrations import run_alembic

pytestmark = pytest.mark.contract

APP_ROLE = "ridematch_app_test"
APP_ROLE_PASSWORD = "ridematch_app_test"


def _url_for(database: str, *, user: str = "ridematch", password: str = "ridematch") -> str:
    base = env.database_url().rsplit("/", 1)[0]
    base = re.sub(r"//[^@]*@", f"//{user}:{password}@", base)
    return f"{base}/{database}"


async def _admin_connection() -> asyncpg.Connection:
    return await asyncpg.connect(env.asyncpg_dsn(_url_for("postgres")))


@pytest.fixture
async def scratch() -> AsyncIterator[str]:
    """A fresh, empty database; yields its SQLAlchemy URL."""
    name = f"ridematch_mig_{uuid.uuid4().hex[:8]}_test"
    try:
        admin = await _admin_connection()
    except OSError as exc:  # pragma: no cover - environment problem
        pytest.skip(f"Cannot reach Postgres: {exc}")
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        yield _url_for(name)
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


async def _fetch(url: str, sql: str) -> list[asyncpg.Record]:
    connection = await asyncpg.connect(env.asyncpg_dsn(url))
    try:
        return await connection.fetch(sql)
    finally:
        await connection.close()


async def _tables(url: str) -> set[str]:
    rows = await _fetch(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row["tablename"] for row in rows}


def _heads() -> list[str]:
    out = run_alembic(env.database_url(), "heads").stdout
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def _current(url: str) -> str:
    out = run_alembic(url, "current").stdout
    return " ".join(line.split()[0] for line in out.splitlines() if line.strip())


def test_there_is_exactly_one_head() -> None:
    assert len(_heads()) == 1, "a branched history needs a merge revision"


async def test_upgrade_from_empty_reaches_head(scratch: str) -> None:
    run_alembic(scratch, "upgrade", "head")
    assert _current(scratch) == _heads()[0]
    assert {"users", "rides", "ride_requests", "ratings", "notifications"} <= await _tables(scratch)


async def test_a_second_upgrade_is_a_no_op(scratch: str) -> None:
    run_alembic(scratch, "upgrade", "head")
    result = run_alembic(scratch, "upgrade", "head")
    assert "Running upgrade" not in result.stderr + result.stdout
    assert _current(scratch) == _heads()[0]


async def test_round_trip_down_to_base_and_back(scratch: str) -> None:
    run_alembic(scratch, "upgrade", "head")
    run_alembic(scratch, "downgrade", "base")
    assert await _tables(scratch) == {"alembic_version"}
    run_alembic(scratch, "upgrade", "head")
    assert _current(scratch) == _heads()[0]


async def test_the_models_match_the_migrations(scratch: str) -> None:
    run_alembic(scratch, "upgrade", "head")
    result = run_alembic(scratch, "check", check=False)
    assert result.returncode == 0, result.stdout + result.stderr


async def test_upgrade_works_without_superuser(scratch: str) -> None:
    """Managed Postgres app roles only get CREATE on their schema."""
    database = scratch.rsplit("/", 1)[-1]
    admin = await _admin_connection()
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", APP_ROLE)
        if not exists:
            await admin.execute(
                f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"PASSWORD '{APP_ROLE_PASSWORD}'"
            )
        await admin.execute(f'GRANT CONNECT ON DATABASE "{database}" TO {APP_ROLE}')
    finally:
        await admin.close()
    owner = await asyncpg.connect(env.asyncpg_dsn(scratch))
    try:
        await owner.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {APP_ROLE}")
    finally:
        await owner.close()

    app_url = _url_for(database, user=APP_ROLE, password=APP_ROLE_PASSWORD)
    run_alembic(app_url, "upgrade", "head")
    assert _current(app_url) == _heads()[0]


# ── schema.sql parity ────────────────────────────────────────────────────

_SNAPSHOT_QUERIES = {
    "columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable,
               coalesce(column_default, '') AS col_default,
               coalesce(character_maximum_length, -1) AS max_len
        FROM information_schema.columns WHERE table_schema = $1
    """,
    "constraints": """
        SELECT cl.relname AS table_name, c.conname, c.contype::text,
               pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = $1
    """,
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = $1",
    "triggers": """
        SELECT cl.relname AS table_name, t.tgname, pg_get_triggerdef(t.oid) AS definition
        FROM pg_trigger t
        JOIN pg_class cl ON cl.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        WHERE n.nspname = $1 AND NOT t.tgisinternal
    """,
    "functions": """
        SELECT p.proname, pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = $1
    """,
}


def _normalise(value: object) -> object:
    if isinstance(value, str):
        return re.sub(r"\b(public|ref)\.", "", value)
    return value


async def _snapshot(connection: asyncpg.Connection, schema: str) -> dict[str, set[tuple]]:
    snapshot: dict[str, set[tuple]] = {}
    for name, sql in _SNAPSHOT_QUERIES.items():
        rows = await connection.fetch(sql, schema)
        snapshot[name] = {
            tuple(_normalise(value) for value in row.values())
            for row in rows
            if "alembic_version" not in row.values()
        }
    return snapshot


async def test_migrations_match_schema_sql(scratch: str) -> None:
    run_alembic(scratch, "upgrade", "head")
    schema_sql = env.SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    connection = await asyncpg.connect(env.asyncpg_dsn(scratch))
    try:
        await connection.execute("CREATE SCHEMA ref")
        await connection.execute("SET search_path TO ref")
        await connection.execute(schema_sql)
        # Neither schema on the path, so every catalog name prints qualified, then normalised.
        await connection.execute("SET search_path TO pg_catalog")
        migrated = await _snapshot(connection, "public")
        reference = await _snapshot(connection, "ref")
    finally:
        await connection.close()

    for kind in _SNAPSHOT_QUERIES:
        assert reference[kind], f"no {kind} read from schema.sql; the comparison would be vacuous"
        missing = reference[kind] - migrated[kind]
        extra = migrated[kind] - reference[kind]
        assert not missing and not extra, (
            f"{kind} differ between alembic head and schema.sql:\n"
            f"  only in schema.sql: {sorted(missing)}\n"
            f"  only in alembic:    {sorted(extra)}"
        )
