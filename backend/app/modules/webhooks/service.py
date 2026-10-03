"""Clerk webhook logic (CONTRACT.md §2 Webhooks, §4 Users): signature check, idempotency on
`svix-id`, and `user.updated`/`user.deleted` (openapi.yaml `/webhooks/clerk`). Every other event
type is a no-op 204.
"""

import base64
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import BadRequest
from app.modules.users.models import ClerkWebhookEvent, User
from app.ws import WsRegistry

logger = logging.getLogger(__name__)


def verify_signature(
    settings: Settings,
    *,
    svix_id: str | None,
    svix_timestamp: str | None,
    svix_signature: str | None,
    body: bytes,
) -> None:
    """The Svix HMAC check `openapi.yaml` describes: `v1,<base64 hmac-sha256>` of
    `{svix_id}.{svix_timestamp}.{body}`, keyed by the part of the signing secret after `whsec_`.
    """
    secret = settings.clerk_webhook_signing_secret
    if not (svix_id and svix_timestamp and svix_signature and secret):
        raise BadRequest()
    try:
        secret_bytes = base64.b64decode(secret.split("_", 1)[1])
    except Exception as exc:
        raise BadRequest() from exc

    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode()

    for candidate in svix_signature.split():
        _, _, signature = candidate.partition(",")
        if signature and hmac.compare_digest(signature, expected):
            return
    raise BadRequest()


def _primary_email(data: dict[str, Any]) -> str | None:
    addresses = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    for address in addresses:
        if address.get("id") == primary_id:
            return address.get("email_address")
    if addresses:
        return addresses[0].get("email_address")
    return None


async def _sync_email(db: AsyncSession, data: dict[str, Any]) -> None:
    clerk_user_id = data.get("id")
    email = _primary_email(data)
    if not clerk_user_id or not email:
        return
    user = (
        await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if user is not None:
        user.email = email.strip().lower()


async def _deactivate(db: AsyncSession, data: dict[str, Any], registry: WsRegistry) -> None:
    clerk_user_id = data.get("id")
    if not clerk_user_id:
        return
    user = (
        await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return
    user.is_active = False
    await registry.close_user(user.id)


async def handle_event(
    db: AsyncSession,
    *,
    svix_id: str,
    event_type: str,
    data: dict[str, Any],
    now: datetime,
    registry: WsRegistry,
) -> None:
    """Deliveries may repeat or arrive out of order; `svix_id` makes this a no-op on a replay."""
    db.add(ClerkWebhookEvent(svix_id=svix_id, event_type=event_type, received_at=now))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return

    if event_type == "user.updated":
        await _sync_email(db, data)
    elif event_type == "user.deleted":
        await _deactivate(db, data, registry)
    else:
        logger.info("Ignoring unhandled Clerk webhook event type %s", event_type)

    await db.commit()
