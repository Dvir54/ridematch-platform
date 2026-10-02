"""Direct access to the test database, independent of the backend's own session.

The schema is loaded from `contracts/schema.sql`, which that file explicitly
invites ("tests may load this file directly into a throwaway DB"). Loading the
contract rather than running the backend's Alembic migration is deliberate: it
is the contract that tests are supposed to prove, so a migration that drifts
from `schema.sql` shows up as failing tests instead of passing ones.

Calls share one lazily created pool. The suite runs on a single session-scoped
event loop (pyproject.toml), so the pool is never used from another loop. Opening
a fresh connection per call used to hit sporadic `ConnectionResetError`s on
Windows during setup.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from . import env

# Tables the suite must not truncate between tests.
PRESERVED_TABLES = frozenset({"alembic_version"})


class TestDatabase:
    __test__ = False  # not a pytest test class

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or env.asyncpg_dsn()
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ── raw access ──────────────────────────────────────────────────────
    async def execute(self, sql: str, *args: Any) -> str:
        pool = await self._get_pool()
        return await pool.execute(sql, *args)

    async def fetch(self, sql: str, *args: Any) -> list[asyncpg.Record]:
        pool = await self._get_pool()
        return await pool.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args: Any) -> asyncpg.Record | None:
        pool = await self._get_pool()
        return await pool.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        pool = await self._get_pool()
        return await pool.fetchval(sql, *args)

    # ── lifecycle ───────────────────────────────────────────────────────
    async def reset_schema(self) -> None:
        """Drop everything and rebuild from contracts/schema.sql."""
        schema_sql = env.SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
            await conn.execute(schema_sql)

    async def table_names(self) -> list[str]:
        rows = await self.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [r["table_name"] for r in rows]

    async def truncate_all(self) -> None:
        names = [n for n in await self.table_names() if n not in PRESERVED_TABLES]
        if not names:
            return
        targets = ", ".join(f'public."{n}"' for n in names)
        await self.execute(f"TRUNCATE {targets} RESTART IDENTITY CASCADE")

    # ── small helpers the factories and tests use ───────────────────────
    async def set_admin(self, user_id: int, value: bool = True) -> None:
        await self.execute("UPDATE users SET is_admin = $2 WHERE id = $1", user_id, value)

    async def set_active(self, user_id: int, value: bool) -> None:
        await self.execute("UPDATE users SET is_active = $2 WHERE id = $1", user_id, value)

    async def set_driver_rating(self, user_id: int, rating: float, count: int = 1) -> None:
        """Set a cached driver rating directly. Ratings themselves have no
        endpoint until Phase 5 (PLAN), so the matching formula's rating
        component (CONTRACT.md §7) can only be exercised this way for now -
        the same exception `set_admin`/`set_active` already rely on."""
        await self.execute(
            "UPDATE users SET driver_rating = $2, driver_rating_count = $3 WHERE id = $1",
            user_id,
            rating,
            count,
        )

    async def user_row(self, user_id: int) -> asyncpg.Record | None:
        return await self.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    async def count(self, table: str) -> int:
        return await self.fetchval(f'SELECT count(*) FROM public."{table}"')
