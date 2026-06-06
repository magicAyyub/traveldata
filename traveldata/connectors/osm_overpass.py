"""OSM / Overpass connector (fallback POI source + tag richness).

Same Connector contract as OpenTripMap, so the pipeline treats them interchangeably.
This is what keeps the design from depending on a single source.
"""
from __future__ import annotations

from typing import Iterator

from ..cache.http_cache import RateLimitedClient
from ..config import settings
from ..normalize import mappers
from .base import CanonicalPoiDraft, Connector, RawDoc, WorkUnit

# Tags worth pulling for a discovery product.
_SELECTORS = ['"tourism"', '"historic"', '"leisure"~"park|garden|nature_reserve"',
              '"natural"~"peak|beach|water|cave_entrance|volcano"']


def build_query(bbox: tuple[float, float, float, float], timeout: int = 60) -> str:
    """bbox = (south, west, north, east). Returns Overpass QL."""
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    parts = []
    for sel in _SELECTORS:
        for typ in ("node", "way", "relation"):
            parts.append(f'  {typ}[{sel}]{box};')
    body = "\n".join(parts)
    return f"[out:json][timeout:{timeout}];\n(\n{body}\n);\nout center tags;"


def _bbox_around(lat: float, lon: float, radius_m: int) -> tuple[float, float, float, float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.1, abs(__import__("math").cos(__import__("math").radians(lat)))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


class OverpassConnector(Connector):
    source = "osm"
    license = mappers.OSM_LICENSE

    def __init__(self, client: RateLimitedClient | None = None, lang: str | None = None):
        self.client = client or RateLimitedClient()
        self.lang = lang or settings.default_lang
        self.url = settings.overpass_url

    def discover(self, lat: float, lon: float, radius_m: int = 5000, **kw) -> Iterator[WorkUnit]:
        yield WorkUnit(lat=lat, lon=lon, radius_m=radius_m,
                       bbox=_bbox_around(lat, lon, radius_m), place_id=kw.get("place_id"))

    def fetch(self, unit: WorkUnit) -> Iterator[RawDoc]:
        bbox = unit.bbox or _bbox_around(unit.lat, unit.lon, unit.radius_m or 5000)
        data = self.client.post_text(self.url, {"data": build_query(bbox)})
        for element in (data or {}).get("elements", []):
            if not element.get("tags"):
                continue
            yield RawDoc(
                source=self.source,
                source_id=f"{element.get('type')}/{element.get('id')}",
                payload=element,
                license=self.license,
                lang=self.lang,
                source_url=f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
            )

    def to_drafts(self, raw: RawDoc) -> list[CanonicalPoiDraft]:
        return mappers.overpass_to_drafts(raw.payload, lang=raw.lang or self.lang)
