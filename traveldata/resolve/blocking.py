"""Blocking helpers. The runner uses PostGIS ST_DWithin for candidate retrieval (more
accurate than geohash prefixes at cell edges); geohash is stored for an alternate path."""
from __future__ import annotations

import pygeohash


def geohash_of(lat: float, lon: float, precision: int = 9) -> str:
    return pygeohash.encode(lat, lon, precision=precision)


def geohash_prefix(gh: str, n: int = 7) -> str:
    return gh[:n]