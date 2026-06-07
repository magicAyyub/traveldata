"""Enrich resolved POIs from Wikidata (content + metrics as a source_record) + pageviews."""
from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import func, select

from ..cache.http_cache import RateLimitedClient
from ..connectors.base import RawDoc
from ..db.base import get_sessionmaker
from ..db.models import Poi, PoiLink
from ..enrich.pageviews import monthly_views
from ..enrich.wikidata import fetch_wikidata
from ..raw.store import land_raw
from .scoring import reconflate_and_score

WIKIDATA_LICENSE = "CC0 (Wikidata)"


def run_enrich(limit: int | None = None, with_pageviews: bool = True,
               refresh: bool = False,
               langs: tuple[str, ...] = ("en", "fr", "es", "de", "it")) -> dict[str, int]:
    Session = get_sessionmaker()
    stats = {"pois": 0, "wikidata_hits": 0, "pageviews": 0}
    with Session() as session:
        q = select(Poi).where(Poi.wikidata_qid.is_not(None))
        if not refresh:
            q = q.where(Poi.enriched_at.is_(None))
        if limit:
            q = q.limit(limit)
        pois = session.scalars(q).all()
        if not pois:
            return stats

        by_qid = {p.wikidata_qid: p for p in pois if p.wikidata_qid}
        coord_rows = session.execute(
            select(Poi.id,
                   func.ST_Y(func.cast(Poi.geom, Geometry)),
                   func.ST_X(func.cast(Poi.geom, Geometry)))
            .where(Poi.id.in_([p.id for p in pois]))
        ).all()
        coords = {pid: (lat, lon) for pid, lat, lon in coord_rows}

        infos = fetch_wikidata(list(by_qid.keys()), langs=langs)
        pv_client = RateLimitedClient()

        for qid, poi in by_qid.items():
            stats["pois"] += 1
            info = infos.get(qid)
            if not info:
                continue
            stats["wikidata_hits"] += 1

            pv = None
            if with_pageviews and info.enwiki_title:
                pv = monthly_views(info.enwiki_title, client=pv_client)
                stats["pageviews"] += 1

            lat, lon = coords.get(poi.id, (None, None))
            payload = {
                "qid": qid, "labels": info.labels, "descriptions": info.descriptions,
                "image": info.image, "sitelinks": info.sitelink_count,
                "enwiki_title": info.enwiki_title, "pageviews_30d": pv,
                "instance_of": info.instance_of,
                "point": {"lat": lat, "lon": lon} if lat is not None else {},
            }
            raw = RawDoc(source="wikidata", source_id=qid, payload=payload,
                         license=WIKIDATA_LICENSE, lang=None,
                         source_url=f"https://www.wikidata.org/wiki/{qid}")
            rec, _ = land_raw(session, raw)
            session.flush()
            rec.poi_id = poi.id
            if session.get(PoiLink, (poi.id, rec.id)) is None:
                session.add(PoiLink(poi_id=poi.id, source_record_id=rec.id,
                                    match_method="wikidata_qid", match_score=1.0))

            reconflate_and_score(session, poi)  # sets sitelink/pageviews/enriched_at from payload
            if stats["pois"] % 50 == 0:
                session.commit()
        session.commit()
    return stats