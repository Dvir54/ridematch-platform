"""Geo helpers for the search/matching tests (CONTRACT.md §7).

Points are placed due north of a base coordinate (same longitude), so
`haversine_km` reduces to `EARTH_RADIUS_KM * delta_latitude_radians` exactly -
letting a test pick a precise km offset without reimplementing the backend's
distance math for anything other than this sanity check.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """The formula CONTRACT.md §7 names - used only to double-check fixtures."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def north(point: tuple[float, float], km: float) -> tuple[float, float]:
    """A point `km` kilometers due north (same longitude) of `point`."""
    lat, lng = point
    return lat + math.degrees(km / EARTH_RADIUS_KM), lng
