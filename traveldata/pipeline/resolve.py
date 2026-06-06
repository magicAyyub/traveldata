"""Resolve unlinked source_records into canonical POIs, then score the merged view.

Incremental: processes records with poi_id IS NULL. For each, find a match (exact QID,
then spatial ST_DWithin + name similarity) or create a new POI; link, re-conflate from
all linked records, and upsert the score. --rebuild re-resolves everything.

Not optimized (per-record spatial + reconflate queries); fine at city scale.
"""
from __future__ import annotations

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, text

from ..db.base import get_sessionmaker
from ..db.models import Poi, PoiLink, PoiScore, SourceRecord
from ..normalize.mappers import record_to_drafts
from ..resolve.blocking import geohash_of
from ..resolve.conflate import conflate
from ..resolve.matcher import name_similarity
from ..score import scorer


def _point(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _find_match(session, draft, max_distance_m: int, name_threshold: float):
    if draft.wikidata_qid:
        poi = session.scalar(select(Poi).where(Poi.wikidata_qid == draft.wikidata_qid))
        if poi:
            return poi, "wikidata_qid", 1.0

    pt = f"SRID=4326;POINT({draft.lon} {draft.lat})"
    dist = func.ST_Distance(Poi.geom, func.ST_GeogFromText(pt))
    rows = session.execute(
        select(Poi, dist.label("d"))
        .where(func.ST_DWithin(Poi.geom, func.ST_GeogFromText(pt), max_distance_m))
        .order_by(dist)
        .limit(10)
    ).all()

    best, best_sim = None, 0.0
    for poi, _d in rows:
        sim = name_similarity(draft.canonical_name, poi.canonical_name)
        if sim >= name_threshold and sim > best_sim:
            best, best_sim = poi, sim
    return (best, "spatial_name", best_sim) if best else (None, None, 0.0)


def _create_poi(session, draft) -> Poi:
    poi = Poi(
        canonical_name=draft.canonical_name,
        names=draft.names,
        geom=_point(draft.lon, draft.lat),
        geohash=geohash_of(draft.lat, draft.lon),
        wikidata_qid=draft.wikidata_qid,
        categories=draft.categories,
        raw_kinds=draft.raw_kinds,
        short_description=draft.short_description,
        descriptions=draft.descriptions,
        images=draft.images,
        source_xids=draft.source_xids,
        field_provenance={},
    )
    session.add(poi)
    return poi


def _upsert_score(session, poi_id, s: scorer.PoiScoreResult) -> None:
    row = session.get(PoiScore, (poi_id, s.model_version))
    if row is None:
        row = PoiScore(poi_id=poi_id, model_version=s.model_version)
        session.add(row)
    row.popularity = s.popularity
    row.content_richness = s.content_richness
    row.activity_score = s.activity_score
    row.hidden_gem_score = s.hidden_gem_score
    row.components = s.components


def _reconflate_and_score(session, poi: Poi) -> None:
    session.flush()  # make the just-set rec.poi_id visible to the query below
    linked = session.scalars(select(SourceRecord).where(SourceRecord.poi_id == poi.id)).all()
    drafts = []
    for r in linked:
        drafts += record_to_drafts(r.source, r.payload, r.lang)
    if not drafts:
        return
    c = conflate(drafts)
    poi.canonical_name = c.canonical_name
    poi.names = c.names
    poi.geom = _point(c.lon, c.lat)
    poi.geohash = geohash_of(c.lat, c.lon)
    poi.wikidata_qid = c.wikidata_qid
    poi.categories = c.categories
    poi.raw_kinds = c.raw_kinds
    poi.short_description = c.short_description
    poi.descriptions = c.descriptions
    poi.images = c.images
    poi.source_xids = c.source_xids
    poi.field_provenance = c.field_provenance

    s = scorer.score(scorer.PoiFeatures(
        categories=c.categories,
        has_coordinates=True,
        description_len=len(c.short_description or ""),
        image_count=len(c.images),
        source_count=len(c.sources),
        lang_count=len(c.names),
        otm_rate=c.importance_raw,
        osm_present="osm" in c.sources,
    ))
    _upsert_score(session, poi.id, s)


def run_resolve(rebuild: bool = False, max_distance_m: int = 80,
                name_threshold: float = 0.85, batch_commit: int = 200) -> dict[str, int]:
    Session = get_sessionmaker()
    stats = {"records": 0, "matched": 0, "created": 0}
    with Session() as session:
        if rebuild:
            session.execute(text("DELETE FROM poi_score"))
            session.execute(text("DELETE FROM poi_link"))
            session.execute(text("UPDATE source_record SET poi_id = NULL"))
            session.execute(text("DELETE FROM poi"))
            session.commit()

        recs = session.scalars(
            select(SourceRecord).where(SourceRecord.poi_id.is_(None))
        ).all()

        for rec in recs:
            drafts = record_to_drafts(rec.source, rec.payload, rec.lang)
            if not drafts:
                continue
            draft = drafts[0]
            stats["records"] += 1

            poi, method, score = _find_match(session, draft, max_distance_m, name_threshold)
            if poi is None:
                poi = _create_poi(session, draft)
                session.flush()  # populate poi.id (DB gen_random_uuid) for linking
                method, score = "new", 1.0
                stats["created"] += 1
            else:
                stats["matched"] += 1

            session.add(PoiLink(poi_id=poi.id, source_record_id=rec.id,
                                match_method=method, match_score=score))
            rec.poi_id = poi.id
            _reconflate_and_score(session, poi)

            if stats["records"] % batch_commit == 0:
                session.commit()
        session.commit()
    return stats