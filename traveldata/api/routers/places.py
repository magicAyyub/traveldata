"""Place endpoints. highlights() is geo-scoped around the place centroid, so it surfaces
the whole POI set in the area, not just the Wikivoyage listings."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geometry
from sqlalchemy import cast, desc, func, select
from sqlalchemy.orm import Session

from ...db.models import Place, Poi, PoiScore, SourceRecord
from ...score.scorer import MODEL_VERSION
from ..attributions import attributions
from ..deps import get_session
from ..schemas import PlaceOut, PoiOut, ScoreOut

router = APIRouter(prefix="/places", tags=["places"])

_SORTS = {
    "hidden_gem_score": PoiScore.hidden_gem_score,
    "activity_score": PoiScore.activity_score,
    "popularity": PoiScore.popularity,
    "content_richness": PoiScore.content_richness,
}
_src_agg = (select(SourceRecord.poi_id.label("pid"),
                   func.array_agg(func.distinct(SourceRecord.source)).label("srcs"))
            .group_by(SourceRecord.poi_id).subquery())


def _xy(session, table, row):
    if row.geom is None:
        return None, None
    g = cast(table.geom, Geometry)
    return session.execute(select(func.ST_Y(g), func.ST_X(g)).where(table.id == row.id)).one()


def _place_out(session, p: Place) -> PlaceOut:
    lat, lon = _xy(session, Place, p)
    return PlaceOut(id=str(p.id), canonical_name=p.canonical_name, level=p.level,
                    names=p.names or {}, lat=lat, lon=lon,
                    descriptions=p.descriptions or {}, practical_info=p.practical_info or {},
                    wikivoyage_title=p.wikivoyage_title)


@router.get("", response_model=list[PlaceOut])
def list_places(session: Session = Depends(get_session)):
    return [_place_out(session, p) for p in session.scalars(select(Place)).all()]


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(place_id: uuid.UUID, session: Session = Depends(get_session)):
    p = session.get(Place, place_id)
    if p is None:
        raise HTTPException(404, "place not found")
    return _place_out(session, p)


@router.get("/{place_id}/highlights", response_model=list[PoiOut])
def highlights(place_id: uuid.UUID, sort: str = Query("hidden_gem_score"),
               radius_m: int = Query(2000, ge=1, le=20000), limit: int = Query(20, ge=1, le=100),
               session: Session = Depends(get_session)):
    if sort not in _SORTS:
        raise HTTPException(422, f"sort must be one of {list(_SORTS)}")
    p = session.get(Place, place_id)
    if p is None:
        raise HTTPException(404, "place not found")
    lat, lon = _xy(session, Place, p)
    if lat is None:
        return []

    pt = func.ST_GeogFromText(f"SRID=4326;POINT({lon} {lat})")
    g = cast(Poi.geom, Geometry)
    rows = session.execute(
        select(Poi, PoiScore, func.ST_Y(g), func.ST_X(g), _src_agg.c.srcs)
        .join(PoiScore, (PoiScore.poi_id == Poi.id) & (PoiScore.model_version == MODEL_VERSION))
        .outerjoin(_src_agg, _src_agg.c.pid == Poi.id)
        .where(func.ST_DWithin(Poi.geom, pt, radius_m))
        .where(Poi.is_destination.is_(True))
        .order_by(desc(_SORTS[sort])).limit(limit)
    ).all()

    out = []
    for poi, sc, plat, plon, srcs in rows:
        out.append(PoiOut(
            id=str(poi.id), canonical_name=poi.canonical_name, names=poi.names or {},
            lat=plat, lon=plon, categories=poi.categories or [],
            short_description=poi.short_description, images=poi.images or [],
            is_destination=poi.is_destination, wikipedia_title=poi.wikipedia_title,
            sitelink_count=poi.sitelink_count, pageviews_30d=poi.pageviews_30d,
            source_xids=poi.source_xids or {}, field_provenance=poi.field_provenance or {},
            scores=ScoreOut(hidden_gem_score=sc.hidden_gem_score, activity_score=sc.activity_score,
                            popularity=sc.popularity, content_richness=sc.content_richness),
            attributions=attributions(srcs),
        ))
    return out