"""Redis is used only for the WebSocket connection registry (CONTRACT.md §2)."""

from redis.asyncio import Redis

from app.config import Settings


def create_redis(settings: Settings) -> Redis:
    """Lazy: no connection is opened until the first command."""
    return Redis.from_url(settings.redis_url, decode_responses=True)
