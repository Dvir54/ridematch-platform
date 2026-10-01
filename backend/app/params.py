"""Query parameters shared by the list endpoints (CONTRACT.md §2 Lists).

`limit`/`offset` mirror `openapi.yaml` #/components/parameters, and `status` filters arrive
comma-separated (`?status=upcoming,full`).
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

from app.errors import UnprocessableEntity

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class Page:
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page:
    return Page(limit=limit, offset=offset)


PageParams = Annotated[Page, Depends(page_params)]

StatusFilter = Annotated[
    str | None,
    Query(description="Comma-separated status filter, e.g. `upcoming,full`"),
]


def parse_status_filter(raw: str | None, allowed: tuple[str, ...]) -> tuple[str, ...]:
    """`"upcoming,full"` -> `("upcoming", "full")`; an unknown value is a 422, as for an enum."""
    if raw is None:
        return ()
    values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise UnprocessableEntity(
            "VALIDATION_ERROR",
            "Unknown status filter.",
            details=[
                {
                    "field": "query.status",
                    "message": f"'{value}' is not one of: {', '.join(allowed)}.",
                }
                for value in unknown
            ],
        )
    return values
