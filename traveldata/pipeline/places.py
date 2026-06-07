"""Ingest a Wikivoyage destination page: upsert a `place`, land its listings as
source_records (resolved on the next `resolve`/`pipeline`)."""
from __future__ import annotations

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from ..connectors.base import RawDoc
from ..connectors.wikivoyage import fetch_wikitext
from ..db.base import get_sessionmaker
from ..db.models import Place
from ..normalize.mappers import WIKIVOYAGE_LICENSE
from ..normalize.wikivoyage_parse import parse_page
from ..raw.store import land_raw


def run_ingest_place(title: str, lang: str = "en", level: str = "city") -> dict:
    parsed = parse_page(fetch_wikitext(title, lang), lang)
    page_url = f"https://{lang}.wikivoyage.org/wiki/{title.replace(' ', '_')}"

    Session = get_sessionmaker()
    with Session() as session:
        place = session.scalar(select(Place).where(Place.wikivoyage_title == title))
        if place is None:
            place = Place(level=level, canonical_name=title.split("/")[-1], wikivoyage_title=title)
            session.add(place)
        place.level = level
        place.names = {lang: title.split("/")[-1]}
        place.descriptions = parsed.descriptions
        place.practical_info = parsed.practical_info
        if parsed.center:
            place.geom = WKTElement(f"POINT({parsed.center[1]} {parsed.center[0]})", srid=4326)
        session.flush()

        landed = 0
        for lst in parsed.listings:
            if lst.lat is None or lst.lon is None:
                continue
            sid = f"{title}#{lst.kind}:{lst.name}"
            payload = {
                "source_id": sid, "kind": lst.kind, "name": lst.name,
                "lat": lst.lat, "lon": lst.lon, "address": lst.address,
                "hours": lst.hours, "price": lst.price, "phone": lst.phone,
                "url": lst.url, "content": lst.content, "wikidata": lst.wikidata,
                "page_url": page_url,
            }
            rec, _ = land_raw(session, RawDoc(
                source="wikivoyage", source_id=sid, payload=payload,
                license=WIKIVOYAGE_LICENSE, lang=lang, source_url=page_url))
            session.flush()
            rec.place_id = place.id
            landed += 1

        session.commit()
        return {"title": title, "place_id": str(place.id), "listings": landed}