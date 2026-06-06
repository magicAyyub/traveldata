"""OpenTripMap connector (primary POI source).

Endpoints used:
  GET /{lang}/places/geoname        name -> {lat, lon, ...}
  GET /{lang}/places/radius         POI list within radius
  GET /{lang}/places/xid/{xid}      full detail for one POI

NOTE: OpenTripMap's free API key has been unreliable. `connectors.osm_overpass`
is a drop-in fallback exposing the same Connector contract.
"""
from __future__ import annotations

from typing import Iterator

from ..cache.http_cache import RateLimitedClient
from ..config import settings
from ..normalize import mappers
from .base import CanonicalPoiDraft, Connector, RawDoc, WorkUnit

DEFAULT_KINDS = (
    "interesting_places,museums,historic,architecture,natural,"
    "cultural,view_points,gardens_and_parks,marketplaces"
)


class OpenTripMapConnector(Connector):
    source = "opentripmap"
    license = mappers.OTM_LICENSE

    def __init__(self, client: RateLimitedClient | None = None, lang: str | None = None):
        self.client = client or RateLimitedClient()
        self.lang = lang or settings.default_lang
        self.base = settings.opentripmap_base_url.rstrip("/")
        self.apikey = settings.opentripmap_api_key

    def _url(self, path: str) -> str:
        return f"{self.base}/{self.lang}/places/{path}"

    def geoname(self, name: str) -> dict:
        return self.client.get_json(self._url("geoname"), {"name": name, "apikey": self.apikey})

    def discover(self, lat: float, lon: float, radius_m: int = 5000, **kw) -> Iterator[WorkUnit]:
        yield WorkUnit(lat=lat, lon=lon, radius_m=radius_m,
                       place_id=kw.get("place_id"), extra={"kinds": kw.get("kinds", DEFAULT_KINDS)})

    def fetch(self, unit: WorkUnit) -> Iterator[RawDoc]:
        listing = self.client.get_json(
            self._url("radius"),
            {
                "radius": unit.radius_m or 5000,
                "lat": unit.lat,
                "lon": unit.lon,
                "kinds": unit.extra.get("kinds", DEFAULT_KINDS),
                "format": "json",
                "limit": unit.extra.get("limit", 200),
                "apikey": self.apikey,
            },
        )
        for item in listing or []:
            xid = item.get("xid")
            if not xid:
                continue
            detail = self.client.get_json(self._url(f"xid/{xid}"), {"apikey": self.apikey})
            yield RawDoc(
                source=self.source,
                source_id=xid,
                payload=detail,
                license=self.license,
                lang=self.lang,
                source_url=detail.get("otm"),
            )

    def to_drafts(self, raw: RawDoc) -> list[CanonicalPoiDraft]:
        return mappers.opentripmap_to_drafts(raw.payload, lang=raw.lang or self.lang)
