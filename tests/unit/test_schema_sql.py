"""The suite builds its database from contracts/schema.sql, so that file has to
load cleanly and the truncation between tests has to really reset state.

These run without the backend; they only need `docker compose up -d`.
"""

from __future__ import annotations

from support.db import TestDatabase

EXPECTED_TABLES = {
    "clerk_webhook_events",
    "notifications",
    "ratings",
    "ride_requests",
    "rides",
    "users",
}


async def test_schema_sql_creates_the_contract_tables(db: TestDatabase) -> None:
    assert EXPECTED_TABLES.issubset(set(await db.table_names()))


async def test_identity_columns_restart_after_truncation(db: TestDatabase) -> None:
    await db.execute(
        """
        INSERT INTO users (clerk_user_id, email, name, date_of_birth, terms_accepted_at)
        VALUES ('user_seed', 'seed@ridematch.test', 'Seed', '1990-01-01', now())
        """
    )
    assert await db.fetchval("SELECT id FROM users WHERE clerk_user_id = 'user_seed'") == 1

    await db.truncate_all()
    assert await db.count("users") == 0

    await db.execute(
        """
        INSERT INTO users (clerk_user_id, email, name, date_of_birth, terms_accepted_at)
        VALUES ('user_seed', 'seed@ridematch.test', 'Seed', '1990-01-01', now())
        """
    )
    assert await db.fetchval("SELECT id FROM users WHERE clerk_user_id = 'user_seed'") == 1


async def test_email_uniqueness_is_case_insensitive(db: TestDatabase) -> None:
    """schema.sql indexes lower(email); the app lowercases before insert."""
    import asyncpg

    await db.execute(
        """
        INSERT INTO users (clerk_user_id, email, name, date_of_birth, terms_accepted_at)
        VALUES ('user_a', 'dup@ridematch.test', 'A', '1990-01-01', now())
        """
    )
    try:
        await db.execute(
            """
            INSERT INTO users (clerk_user_id, email, name, date_of_birth, terms_accepted_at)
            VALUES ('user_b', 'DUP@ridematch.test', 'B', '1990-01-01', now())
            """
        )
    except asyncpg.UniqueViolationError:
        return
    raise AssertionError("lower(email) is not unique in contracts/schema.sql")
