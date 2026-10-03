"""Run the backend's Alembic, the same command the production release step runs.

In a subprocess on purpose: `alembic/env.py` calls `asyncio.run()` (which can't run inside
pytest's event loop) and `fileConfig()` (which would reconfigure the suite's logging).
"""

from __future__ import annotations

import os
import subprocess
import sys

from . import env

BACKEND_DIR = env.REPO_ROOT / "backend"


def run_alembic(database_url: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """`alembic <args>` against `database_url` (a SQLAlchemy URL)."""
    process_env = {
        **os.environ,
        "APP_ENV": "test",
        "TEST_DATABASE_URL": database_url,
        "DATABASE_URL": database_url,
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"alembic {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result
