"""Ride logic. Phase 1 needs only the open-ride count that gates removing a vehicle."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rides.models import OPEN_RIDE_STATUSES, Ride


async def count_open_rides_for_driver(db: AsyncSession, driver_id: int) -> int:
    """Rides the driver still has `upcoming` or `full` (CONTRACT.md §4 Vehicles)."""
    stmt = (
        select(func.count())
        .select_from(Ride)
        .where(Ride.driver_id == driver_id, Ride.status.in_(OPEN_RIDE_STATUSES))
    )
    return int((await db.execute(stmt)).scalar_one())
