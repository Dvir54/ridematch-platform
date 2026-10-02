"""`POST /webhooks/clerk` — called by Clerk via Svix, never by the frontend. No `CurrentUser`
dependency here, so (like `/health`) it needs no session token (CONTRACT.md §2).
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel

from app.auth.deps import AppSettings
from app.clock import Now
from app.db import DbSession
from app.errors import BadRequest
from app.modules.webhooks import service as webhooks_service
from app.ws import WsRegistryDep

router = APIRouter(tags=["webhooks"])


class _ClerkEvent(BaseModel):
    type: str
    data: dict[str, Any]


@router.post(
    "/webhooks/clerk",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clerk webhook (Svix-signed)",
)
async def clerk_webhook(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    now: Now,
    registry: WsRegistryDep,
    svix_id: Annotated[str | None, Header()] = None,
    svix_timestamp: Annotated[str | None, Header()] = None,
    svix_signature: Annotated[str | None, Header()] = None,
) -> Response:
    body = await request.body()
    webhooks_service.verify_signature(
        settings,
        svix_id=svix_id,
        svix_timestamp=svix_timestamp,
        svix_signature=svix_signature,
        body=body,
    )
    try:
        event = _ClerkEvent.model_validate(json.loads(body))
    except (ValueError, TypeError) as exc:
        raise BadRequest() from exc

    await webhooks_service.handle_event(
        db,
        svix_id=svix_id,
        event_type=event.type,
        data=event.data,
        now=now,
        registry=registry,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
