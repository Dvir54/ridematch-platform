"""Server-side admin tasks: `cd backend && uv run python -m app.admin_cli grant|revoke <email>`.

The only way to make an admin in production (CONTRACT.md §4 Users). Idempotent: granting an admin
or revoking a non-admin succeeds and says so. Refuses unknown or deactivated users; exits 1 then.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.models import User
from app.modules.users.service import normalise_email


async def set_admin(email: str, value: bool, settings: Settings) -> tuple[bool, str]:
    """Returns (ok, message)."""
    email = normalise_email(email)
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as db, db.begin():
            user = (
                await db.execute(select(User).where(func.lower(User.email) == email))
            ).scalar_one_or_none()
            if user is None:
                return False, f"No user with email {email}."
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
    parser.add_argument("command", choices=["grant", "revoke"])
    parser.add_argument("email")
    args = parser.parse_args(argv)
    ok, message = await set_admin(args.email, args.command == "grant", settings or get_settings())
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()
