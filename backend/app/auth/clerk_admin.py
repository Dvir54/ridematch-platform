"""Clerk Backend API: ban/unban a user (CONTRACT.md §4 Users — admin deactivate/reactivate).

Best-effort: `users.is_active` is what every request actually checks, so a failed call here is
logged and swallowed rather than raised — the DB change still applies either way.
"""

import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

CLERK_API_BASE = "https://api.clerk.com/v1"


async def _call(settings: Settings, clerk_user_id: str, action: str) -> None:
    if not settings.clerk_secret_key:
        logger.warning("CLERK_SECRET_KEY not set; skipping Clerk %s for %s", action, clerk_user_id)
        return
    url = f"{CLERK_API_BASE}/users/{clerk_user_id}/{action}"
    headers = {"Authorization": f"Bearer {settings.clerk_secret_key}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, headers=headers)
            response.raise_for_status()
    except Exception:
        logger.exception("Clerk %s failed for user %s", action, clerk_user_id)


async def ban_user(settings: Settings, clerk_user_id: str) -> None:
    await _call(settings, clerk_user_id, "ban")


async def unban_user(settings: Settings, clerk_user_id: str) -> None:
    await _call(settings, clerk_user_id, "unban")
