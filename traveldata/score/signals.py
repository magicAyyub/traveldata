"""Interpretable scoring signals. Each returns a value in [0, 1].

All inputs are explicit dataclasses so a future learning-to-rank model can train on
the exact same features. Production should z-score popularity against the corpus;
here we use bounded monotone transforms so results are deterministic and testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..normalize import taxonomy


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class RichnessInputs:
    has_description: bool
    description_len: int
    image_count: int
    source_count: int
    has_practical_info: bool
    lang_count: int


def content_richness(i: RichnessInputs) -> float:
    return _clamp(
        0.20 * (1.0 if i.has_description else 0.0)
        + 0.20 * _clamp(i.description_len / 1500.0)
        + 0.15 * _clamp(i.image_count / 3.0)
        + 0.20 * _clamp(i.source_count / 4.0)
        + 0.15 * (1.0 if i.has_practical_info else 0.0)
        + 0.10 * _clamp(i.lang_count / 3.0)
    )


@dataclass
class PopularityInputs:
    pageviews_30d: int | None = None
    sitelink_count: int | None = None
    otm_rate: float | None = None  # 1..7
    osm_present: bool = False


def popularity(i: PopularityInputs) -> float:
    """Weighted mean over the *evidence* signals that are present.

    pageviews / sitelinks / otm_rate are real popularity evidence. osm_present is only
    a weak prior: it provides a small floor when no evidence exists and a tiny nudge
    otherwise -- it must never dominate (a place merely existing in OSM isn't 'famous').
    """
    evidence: list[tuple[float, float]] = []  # (value, weight)
    if i.pageviews_30d is not None:
        evidence.append((_clamp(math.log10(i.pageviews_30d + 1) / 5.0), 0.55))  # ~100k -> 1.0
    if i.sitelink_count is not None:
        evidence.append((_clamp(i.sitelink_count / 40.0), 0.30))
    if i.otm_rate is not None:
        evidence.append((_clamp((i.otm_rate - 1.0) / 6.0), 0.15))

    if not evidence:
        return 0.10 if i.osm_present else 0.0

    total_w = sum(w for _, w in evidence)
    base = sum(v * w for v, w in evidence) / total_w
    nudge = 0.05 if i.osm_present else 0.0
    return _clamp(base + nudge)


def activity_score(categories: list[str], in_wikivoyage_do: bool = False,
                   osm_leisure_sport: bool = False) -> float:
    base = taxonomy.activity_prior(categories)
    return _clamp(base + 0.30 * in_wikivoyage_do + 0.20 * osm_leisure_sport)


def hidden_gem_score(richness: float, pop: float, *, has_coordinates: bool,
                     source_count: int, has_description: bool,
                     offbeat_boost: bool = False) -> float:
    """Interesting but not famous, gated by a quality floor so junk can't win."""
    quality_floor = has_coordinates and (has_description or source_count >= 2)
    if not quality_floor:
        return 0.0
    boost = 0.6 + 0.4 * (1.0 if offbeat_boost else 0.0)
    return _clamp(richness * (1.0 - pop) * boost)
