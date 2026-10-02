"""Builds signed Clerk/Svix webhook deliveries (CONTRACT.md §2 Webhooks,
openapi.yaml `/webhooks/clerk`).

Mirrors the backend's own verification exactly (`app/modules/webhooks/service.py
verify_signature`): `secret` is `whsec_<base64>`, and the signed content is
`{svix_id}.{svix_timestamp}.{raw_body}` HMAC-SHA256'd with the base64-decoded
half after the `whsec_` prefix. A test helper that re-derived this a different
way would only prove the two implementations agree with each other, not that
either is right - so this follows the contract's own description, not the
backend's code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import time
from typing import Any

from . import env

_svix_id_counter = itertools.count(1)


def unique_svix_id() -> str:
    return f"msg_test_{next(_svix_id_counter):04d}"


def event_body(event_type: str, data: dict[str, Any]) -> bytes:
    return json.dumps({"type": event_type, "data": data}).encode()


def sign(
    *,
    svix_id: str,
    body: bytes,
    svix_timestamp: str | None = None,
    secret: str = env.CLERK_WEBHOOK_SIGNING_SECRET,
) -> dict[str, str]:
    """The three `svix-*` headers `clerkWebhook` requires."""
    timestamp = svix_timestamp or str(int(time.time()))
    secret_bytes = base64.b64decode(secret.split("_", 1)[1])
    signed_content = f"{svix_id}.{timestamp}.{body.decode()}".encode()
    signature = base64.b64encode(
        hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": svix_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
    }


def user_updated_data(clerk_user_id: str, *, email: str) -> dict[str, Any]:
    """A minimal Clerk `user.updated` payload with one primary email address."""
    return {
        "id": clerk_user_id,
        "email_addresses": [{"id": "idn_primary", "email_address": email}],
        "primary_email_address_id": "idn_primary",
    }


def user_deleted_data(clerk_user_id: str) -> dict[str, Any]:
    return {"id": clerk_user_id, "deleted": True}
