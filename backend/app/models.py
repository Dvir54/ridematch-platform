"""Imports every model so `Base.metadata` is complete (for Alembic and tests)."""

from app.db import Base
from app.modules.feedback.models import Rating
from app.modules.notifications.models import Notification
from app.modules.requests.models import RideRequest
from app.modules.rides.models import Ride
from app.modules.users.models import ClerkWebhookEvent, User

__all__ = ["Base", "ClerkWebhookEvent", "Notification", "Rating", "Ride", "RideRequest", "User"]
