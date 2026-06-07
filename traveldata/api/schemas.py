from __future__ import annotations

from pydantic import BaseModel


class ScoreOut(BaseModel):
    hidden_gem_score: float | None = None
    activity_score: float | None = None
    popularity: float | None = None
    content_richness: float | None = None


class PoiOut(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = {}
    lat: float
    lon: float
    categories: list[str] = []
    short_description: str | None = None
    images: list[dict] = []
    is_destination: bool = True
    wikipedia_title: str | None = None
    sitelink_count: int | None = None
    pageviews_30d: int | None = None
    source_xids: dict[str, str] = {}
    field_provenance: dict = {}
    scores: ScoreOut = ScoreOut()
    attributions: list[str] = []
    distance_m: float | None = None


class PoiDetailOut(PoiOut):
    descriptions: dict[str, str] = {}