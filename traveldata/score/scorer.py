"""Combine signals into a versioned score. `components` is persisted for training."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import signals

MODEL_VERSION = "heuristic-v1"


@dataclass
class PoiFeatures:
    """The conflated, enriched view of a POI that scoring consumes."""

    categories: list[str]
    has_coordinates: bool
    description_len: int = 0
    image_count: int = 0
    source_count: int = 1
    lang_count: int = 1
    has_practical_info: bool = False
    in_wikivoyage_do: bool = False
    osm_leisure_sport: bool = False
    offbeat_boost: bool = False
    pageviews_30d: int | None = None
    sitelink_count: int | None = None
    otm_rate: float | None = None
    osm_present: bool = False
    is_destination: bool = True


@dataclass
class PoiScoreResult:
    popularity: float
    content_richness: float
    activity_score: float
    hidden_gem_score: float
    model_version: str = MODEL_VERSION
    components: dict = field(default_factory=dict)


def score(f: PoiFeatures) -> PoiScoreResult:
    richness = signals.content_richness(
        signals.RichnessInputs(
            has_description=f.description_len > 0,
            description_len=f.description_len,
            image_count=f.image_count,
            source_count=f.source_count,
            has_practical_info=f.has_practical_info,
            lang_count=f.lang_count,
        )
    )
    pop = signals.popularity(
        signals.PopularityInputs(
            pageviews_30d=f.pageviews_30d,
            sitelink_count=f.sitelink_count,
            otm_rate=f.otm_rate,
            osm_present=f.osm_present,
        )
    )
    activity = signals.activity_score(f.categories, f.in_wikivoyage_do, f.osm_leisure_sport)
    gem = (
        signals.hidden_gem_score(
            richness, pop, has_coordinates=f.has_coordinates,
            source_count=f.source_count, has_description=f.description_len > 0,
            offbeat_boost=f.offbeat_boost,
        )
        if f.is_destination else 0.0
    )
    return PoiScoreResult(
        popularity=round(pop, 4),
        content_richness=round(richness, 4),
        activity_score=round(activity, 4),
        hidden_gem_score=round(gem, 4),
        components={
            "categories": f.categories,
            "source_count": f.source_count,
            "pageviews_30d": f.pageviews_30d,
            "sitelink_count": f.sitelink_count,
            "otm_rate": f.otm_rate,
        },
    )
