"""Shared: re-derive a POI from its linked records, conflate, and (re)score.
Used by both resolve and enrich so scoring logic lives in one place."""
from __future__ import annotations

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select

from ..db.models import Poi, PoiScore, SourceRecord
from ..normalize.mappers import record_to_drafts
from ..resolve.blocking import geohash_of
from ..resolve.conflate import conflate
from ..normalize import taxonomy
from ..score import scorer


def point_wkt(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def upsert_score(session, poi_id, s: scorer.PoiScoreResult) -> None:
    row = session.get(PoiScore, (poi_id, s.model_version))
    if row is None:
        row = PoiScore(poi_id=poi_id, model_version=s.model_version)
        session.add(row)
    row.popularity = s.popularity
    row.content_richness = s.content_richness
    row.activity_score = s.activity_score
    row.hidden_gem_score = s.hidden_gem_score
    row.components = s.components


def reconflate_and_score(session, poi: Poi) -> None:
    session.flush()
    linked = session.scalars(select(SourceRecord).where(SourceRecord.poi_id == poi.id)).all()
    drafts = []
    wd_payload = None
    for r in linked:
        drafts += record_to_drafts(r.source, r.payload, r.lang)
        if r.source == "wikidata":
            wd_payload = r.payload
    if not drafts:
        return

    c = conflate(drafts)
    poi.canonical_name = c.canonical_name
    poi.names = c.names
    poi.geom = point_wkt(c.lon, c.lat)
    poi.geohash = geohash_of(c.lat, c.lon)
    poi.wikidata_qid = c.wikidata_qid
    poi.categories = c.categories
    poi.raw_kinds = c.raw_kinds
    poi.short_description = c.short_description
    poi.descriptions = c.descriptions
    poi.images = c.images
    poi.source_xids = c.source_xids
    poi.field_provenance = c.field_provenance

    # Enrichment metrics come from the Wikidata source_record payload (provenance),
    # so they survive resolve --rebuild without re-fetching.
    if wd_payload is not None:
        poi.sitelink_count = wd_payload.get("sitelinks")
        poi.pageviews_30d = wd_payload.get("pageviews_30d")
        poi.wikipedia_title = wd_payload.get("enwiki_title")
        if "sitelinks" in wd_payload:  # new-style enriched payload
            poi.enriched_at = func.now()

    has_practical = False
    for r in linked:
        if r.source == "osm":
            tags = r.payload.get("tags") or {}
            if any(k in tags for k in ("opening_hours", "website", "contact:website", "phone", "fee")):
                has_practical = True
        elif r.source == "opentripmap":
            if r.payload.get("address") or r.payload.get("url"):
                has_practical = True

    wd_instances = (wd_payload or {}).get("instance_of") or []
    is_dest = taxonomy.is_destination(c.categories, wd_instances)
    poi.is_destination = is_dest

    desc_len = max((len(v) for v in (c.descriptions or {}).values()),
                   default=len(c.short_description or ""))

    s = scorer.score(scorer.PoiFeatures(
        categories=c.categories, has_coordinates=True,
        description_len=desc_len, image_count=len(c.images),
        source_count=len(c.sources), lang_count=len(c.names),
        otm_rate=c.importance_raw, osm_present="osm" in c.sources,
        sitelink_count=poi.sitelink_count, pageviews_30d=poi.pageviews_30d,
        is_destination=is_dest,
        has_practical_info=has_practical,
    ))
    upsert_score(session, poi.id, s)