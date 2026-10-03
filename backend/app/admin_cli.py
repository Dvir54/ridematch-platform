"""Server-side admin tasks: `cd backend && uv run python -m app.admin_cli <command> <email>`.

- `grant` / `revoke`: the only way to make an admin in production (CONTRACT.md §4 Users).
  Idempotent; refuses unknown or deactivated users.
- `anonymise`: a deletion request made outside Clerk. Same effect as the `user.deleted` webhook,
  except that open sockets close only when they next drop (this runs in another process); the
  account is deactivated, so every REST call is refused straight away.

Exits 1 on failure.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.models import User
from app.modules.users.service import anonymise, normalise_email


async def _find(db: AsyncSession, email: str) -> User | None:
    return (
        await db.execute(select(User).where(func.lower(User.email) == normalise_email(email)))
    ).scalar_one_or_none()


async def anonymise_user(email: str, settings: Settings) -> tuple[bool, str]:
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as db, db.begin():
            user = await _find(db, email)
            if user is None:
                return False, f"No user with email {normalise_email(email)}."
            anonymise(user)
            return True, f"User {user.id} anonymised and deactivated."
    finally:
        await engine.dispose()


async def set_admin(email: str, value: bool, settings: Settings) -> tuple[bool, str]:
    """Returns (ok, message)."""
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as db, db.begin():
            user = await _find(db, email)
            if user is None:
                return False, f"No user with email {normalise_email(email)}."
            if not user.is_active:
                return False, f"User {user.id} is deactivated."
            if user.is_admin == value:
                return True, f"User {user.id} already {'is' if value else 'is not'} an admin."
            user.is_admin = value
            return True, f"User {user.id} {'granted' if value else 'revoked'} admin."
    finally:
        await engine.dispose()


async def run(argv: list[str], settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin_cli")
    parser.add_argument("command", choices=["grant", "revoke", "anonymise"])
    parser.add_argument("email")
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    if args.command == "anonymise":
        ok, message = await anonymise_user(args.email, settings)
    else:
        ok, message = await set_admin(args.email, args.command == "grant", settings)
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
