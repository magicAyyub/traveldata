"""Merge a cluster of drafts into one canonical POI with field-level provenance.

Priorities are per-field on purpose: OSM/Wikidata win coordinates; Wikidata/OSM win
names; Wikivoyage/OTM win descriptive prose. Multilingual fields are unioned, with the
higher-priority source winning per language.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..connectors.base import CanonicalPoiDraft

GEOM_PRIORITY = ["osm", "wikidata", "opentripmap"]
NAME_PRIORITY = ["wikidata", "osm", "wikivoyage", "opentripmap"]
DESC_PRIORITY = ["wikivoyage", "opentripmap", "osm", "wikidata"]


@dataclass
class ConflatedPoi:
    canonical_name: str
    lat: float
    lon: float
    names: dict[str, str]
    wikidata_qid: str | None
    categories: list[str]
    raw_kinds: list[str]
    short_description: str | None
    descriptions: dict[str, str]
    images: list[dict]
    source_xids: dict[str, str]
    importance_raw: float | None
    heritage: bool
    field_provenance: dict[str, str | None]
    sources: list[str]


def _rank(source: str, priority: list[str]) -> int:
    return priority.index(source) if source in priority else len(priority)


def _merge_dict(drafts: list[CanonicalPoiDraft], priority: list[str], attr: str) -> dict:
    out: dict[str, str] = {}
    for d in sorted(drafts, key=lambda d: _rank(d.source, priority)):
        for k, v in getattr(d, attr).items():
            if v:
                out.setdefault(k, v)
    return out


def _union(drafts: list[CanonicalPoiDraft], attr: str) -> list:
    out: list = []
    for d in drafts:
        for v in getattr(d, attr):
            if v not in out:
                out.append(v)
    return out


def conflate(drafts: list[CanonicalPoiDraft], default_lang: str = "en") -> ConflatedPoi:
    geom_draft = min(drafts, key=lambda d: _rank(d.source, GEOM_PRIORITY))
    name_draft = min(drafts, key=lambda d: _rank(d.source, NAME_PRIORITY))
    desc_pool = [d for d in drafts if d.short_description or d.descriptions]
    desc_draft = min(desc_pool, key=lambda d: _rank(d.source, DESC_PRIORITY)) if desc_pool else None

    names = _merge_dict(drafts, NAME_PRIORITY, "names")
    descriptions = _merge_dict(drafts, DESC_PRIORITY, "descriptions")
    canonical = names.get(default_lang) or name_draft.canonical_name

    images, seen = [], set()
    for d in drafts:
        for img in d.images:
            u = img.get("url")
            if u and u not in seen:
                seen.add(u)
                images.append(img)

    source_xids: dict[str, str] = {}
    for d in sorted(drafts, key=lambda d: _rank(d.source, NAME_PRIORITY)):
        for k, v in d.source_xids.items():
            source_xids.setdefault(k, v)

    qid_draft = next((d for d in sorted(drafts, key=lambda d: _rank(d.source, NAME_PRIORITY))
                      if d.wikidata_qid), None)
    importances = [d.importance_raw for d in drafts if d.importance_raw is not None]

    short_desc = (desc_draft.short_description if desc_draft and desc_draft.short_description
                  else (next(iter(descriptions.values()))[:280] if descriptions else None))

    return ConflatedPoi(
        canonical_name=canonical,
        lat=geom_draft.lat,
        lon=geom_draft.lon,
        names=names,
        wikidata_qid=qid_draft.wikidata_qid if qid_draft else None,
        categories=_union(drafts, "categories"),
        raw_kinds=_union(drafts, "raw_kinds"),
        short_description=short_desc,
        descriptions=descriptions,
        images=images,
        source_xids=source_xids,
        importance_raw=max(importances) if importances else None,
        heritage=any(d.heritage for d in drafts),
        field_provenance={
            "geom": geom_draft.source,
            "canonical_name": name_draft.source,
            "short_description": desc_draft.source if desc_draft else None,
            "wikidata_qid": qid_draft.source if qid_draft else None,
        },
        sources=sorted({d.source for d in drafts}),
    )