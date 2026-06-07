"""POI endpoints: spatial discovery + detail, ordered by the scores you built."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geometry
from sqlalchemy import cast, desc, func, select
from sqlalchemy.orm import Session

from ...db.models import Poi, PoiScore, SourceRecord
from ...score.scorer import MODEL_VERSION
from ..attributions import attributions
from ..deps import get_session
from ..schemas import PoiDetailOut, PoiOut, ScoreOut

router = APIRouter(prefix="/pois", tags=["pois"])

_SORTS = {
    "hidden_gem_score": PoiScore.hidden_gem_score,
    "activity_score": PoiScore.activity_score,
    "popularity": PoiScore.popularity,
    "content_richness": PoiScore.content_richness,
}

_src_agg = (
    select(SourceRecord.poi_id.label("pid"),
           func.array_agg(func.distinct(SourceRecord.source)).label("srcs"))
    .group_by(SourceRecord.poi_id).subquery()
)


def _geom_xy():
    g = cast(Poi.geom, Geometry)
    return func.ST_Y(g).label("lat"), func.ST_X(g).label("lon")


def _scores(sc: PoiScore | None) -> ScoreOut:
    if sc is None:
        return ScoreOut()
    return ScoreOut(hidden_gem_score=sc.hidden_gem_score, activity_score=sc.activity_score,
                    popularity=sc.popularity, content_richness=sc.content_richness)


@router.get("/nearby", response_model=list[PoiOut])
def nearby(
    lat: float = Query(...), lon: float = Query(...),
    radius_m: int = Query(2000, ge=1, le=50000),
    categories: str | None = Query(None, description="comma-separated; matches any"),
    min_hidden_gem: float = Query(0.0, ge=0.0, le=1.0),
    sort: str = Query("hidden_gem_score"),
    destinations_only: bool = Query(True),
    limit: int = Query(30, ge=1, le=200),
    session: Session = Depends(get_session),
):
    if sort not in _SORTS and sort != "distance":
        raise HTTPException(422, f"sort must be 'distance' or one of {list(_SORTS)}")

    pt = func.ST_GeogFromText(f"SRID=4326;POINT({lon} {lat})")
    dist = func.ST_Distance(Poi.geom, pt)
    lat_c, lon_c = _geom_xy()

    q = (select(Poi, PoiScore, dist.label("distance_m"), lat_c, lon_c, _src_agg.c.srcs)
         .join(PoiScore, (PoiScore.poi_id == Poi.id) & (PoiScore.model_version == MODEL_VERSION))
         .outerjoin(_src_agg, _src_agg.c.pid == Poi.id)
         .where(func.ST_DWithin(Poi.geom, pt, radius_m)))

    if destinations_only:
        q = q.where(Poi.is_destination.is_(True))
    if categories:
        q = q.where(Poi.categories.overlap([c.strip() for c in categories.split(",") if c.strip()]))
    if min_hidden_gem > 0:
        q = q.where(PoiScore.hidden_gem_score >= min_hidden_gem)
    q = q.order_by(dist if sort == "distance" else desc(_SORTS[sort])).limit(limit)

    out = []
    for poi, sc, distance_m, plat, plon, srcs in session.execute(q).all():
        out.append(PoiOut(
            id=str(poi.id), canonical_name=poi.canonical_name, names=poi.names or {},
            lat=plat, lon=plon, categories=poi.categories or [],
            short_description=poi.short_description, images=poi.images or [],
            is_destination=poi.is_destination, wikipedia_title=poi.wikipedia_title,
            sitelink_count=poi.sitelink_count, pageviews_30d=poi.pageviews_30d,
            source_xids=poi.source_xids or {}, field_provenance=poi.field_provenance or {},
            scores=_scores(sc), attributions=attributions(srcs),
            distance_m=round(distance_m, 1) if distance_m is not None else None,
        ))
    return out


@router.get("/{poi_id}", response_model=PoiDetailOut)
def get_poi(poi_id: uuid.UUID, session: Session = Depends(get_session)):
    poi = session.get(Poi, poi_id)
    if poi is None:
        raise HTTPException(404, "POI not found")
    sc = session.get(PoiScore, (poi.id, MODEL_VERSION))
    lat_c, lon_c = _geom_xy()
    plat, plon = session.execute(select(lat_c, lon_c).where(Poi.id == poi.id)).one()
    srcs = session.scalars(
        select(func.distinct(SourceRecord.source)).where(SourceRecord.poi_id == poi.id)
    ).all()
    return PoiDetailOut(
        id=str(poi.id), canonical_name=poi.canonical_name, names=poi.names or {},
        lat=plat, lon=plon, categories=poi.categories or [],
        short_description=poi.short_description, descriptions=poi.descriptions or {},
        images=poi.images or [], is_destination=poi.is_destination,
        wikipedia_title=poi.wikipedia_title, sitelink_count=poi.sitelink_count,
        pageviews_30d=poi.pageviews_30d, source_xids=poi.source_xids or {},
        field_provenance=poi.field_provenance or {}, scores=_scores(sc),
        attributions=attributions(srcs),
    )