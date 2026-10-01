"""The one place `now` comes from.

Business logic never calls `datetime.now()`; services take `now` as a parameter and routers
get it from the `Now` dependency, which tests override to freeze time.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends


def utc_now() -> datetime:
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(utc_now)]
