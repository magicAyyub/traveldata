"""Pure source->canonical mappers. No network, no DB -- fully unit-testable."""
from __future__ import annotations

from typing import Optional

from ..connectors.base import CanonicalPoiDraft
from . import taxonomy

OTM_LICENSE = "ODbL / CC-BY-SA (aggregated via OpenTripMap)"
OSM_LICENSE = "ODbL (OpenStreetMap contributors)"

_OSM_PREFIX = {"N": "node", "W": "way", "R": "relation"}


def _parse_otm_rate(rate) -> tuple[Optional[float], bool]:
    """OTM `rate` like '7h' -> (7.0, heritage=True). '3' -> (3.0, False)."""
    if rate is None:
        return None, False
    s = str(rate).strip().lower()
    heritage = "h" in s
    digits = "".join(ch for ch in s if ch.isdigit())
    return (float(digits) if digits else None), heritage


def _xid_to_osm(xid: Optional[str]) -> Optional[str]:
    """OTM xids embed the OSM ref: 'W12345' -> 'way/12345'."""
    if xid and len(xid) > 1 and xid[0] in _OSM_PREFIX and xid[1:].isdigit():
        return f"{_OSM_PREFIX[xid[0]]}/{xid[1:]}"
    return None


def opentripmap_to_drafts(payload: dict, lang: str = "en") -> list[CanonicalPoiDraft]:
    """Map an OpenTripMap /xid/{xid} detail payload to a canonical draft."""
    name = (payload.get("name") or "").strip()
    point = payload.get("point") or {}
    lat, lon = point.get("lat"), point.get("lon")
    if not name or lat is None or lon is None:
        return []  # unusable without name + coordinates

    xid = payload.get("xid")
    importance, heritage = _parse_otm_rate(payload.get("rate"))

    # description: prefer the Wikipedia extract, then the inline descr
    extracts = payload.get("wikipedia_extracts") or {}
    descr = (extracts.get("text") or (payload.get("info") or {}).get("descr") or "").strip()
    descriptions = {lang: descr} if descr else {}

    images = []
    if payload.get("image"):
        images.append({"url": payload["image"], "source": "opentripmap", "license": "unknown"})
    preview = payload.get("preview") or {}
    if preview.get("source"):
        images.append({"url": preview["source"], "source": "opentripmap", "license": "unknown"})

    source_xids = {"opentripmap": xid} if xid else {}
    if payload.get("wikidata"):
        source_xids["wikidata"] = payload["wikidata"]
    osm = _xid_to_osm(xid)
    if osm:
        source_xids["osm"] = osm

    return [
        CanonicalPoiDraft(
            source="opentripmap",
            source_id=xid or name,
            canonical_name=name,
            lat=float(lat),
            lon=float(lon),
            names={lang: name},
            wikidata_qid=payload.get("wikidata"),
            categories=taxonomy.map_otm_kinds(payload.get("kinds")),
            raw_kinds=[k.strip() for k in (payload.get("kinds") or "").split(",") if k.strip()],
            short_description=(descr[:280] or None) if descr else None,
            descriptions=descriptions,
            images=images,
            source_xids=source_xids,
            importance_raw=importance,
            heritage=heritage,
            license=OTM_LICENSE,
            source_url=payload.get("otm"),
        )
    ]


def overpass_to_drafts(element: dict, lang: str = "en") -> list[CanonicalPoiDraft]:
    """Map one OSM Overpass element (node/way/relation w/ tags) to a draft."""
    tags = element.get("tags") or {}
    name = (tags.get(f"name:{lang}") or tags.get("name") or "").strip()
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:  # way / relation come back with a `center` when queried `out center`
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if not name or lat is None or lon is None:
        return []

    names = {lang: name}
    for k, v in tags.items():
        if k.startswith("name:") and len(k) == 7:  # name:xx
            names[k.split(":", 1)[1]] = v

    osm_id = f"{element.get('type')}/{element.get('id')}"
    source_xids = {"osm": osm_id}
    if tags.get("wikidata"):
        source_xids["wikidata"] = tags["wikidata"]

    images = []
    if tags.get("image"):
        images.append({"url": tags["image"], "source": "osm", "license": "unknown"})

    return [
        CanonicalPoiDraft(
            source="osm",
            source_id=osm_id,
            canonical_name=name,
            lat=float(lat),
            lon=float(lon),
            names=names,
            wikidata_qid=tags.get("wikidata"),
            categories=taxonomy.map_osm_tags(tags),
            raw_kinds=[f"{k}={v}" for k, v in tags.items()
                       if k in {"tourism", "historic", "leisure", "natural", "amenity", "sport"}],
            short_description=tags.get("description"),
            descriptions={lang: tags["description"]} if tags.get("description") else {},
            images=images,
            source_xids=source_xids,
            importance_raw=None,
            heritage=bool(tags.get("heritage")),
            license=OSM_LICENSE,
            source_url=f"https://www.openstreetmap.org/{osm_id}",
        )
    ]

def wikidata_to_drafts(payload: dict, lang: str = "en") -> list[CanonicalPoiDraft]:
    qid = payload.get("qid")
    point = payload.get("point") or {}
    lat, lon = point.get("lat"), point.get("lon")
    labels = payload.get("labels") or {}
    name = labels.get(lang) or next(iter(labels.values()), None)
    if not name or lat is None or lon is None:
        return []
    descriptions = payload.get("descriptions") or {}
    images = ([{"url": payload["image"], "source": "wikidata", "license": "varies"}]
              if payload.get("image") else [])
    return [CanonicalPoiDraft(
        source="wikidata", source_id=qid, canonical_name=name,
        lat=float(lat), lon=float(lon), names=dict(labels), wikidata_qid=qid,
        categories=[], raw_kinds=[],
        short_description=next(iter(descriptions.values()), None),
        descriptions=descriptions, images=images,
        source_xids={"wikidata": qid}, license="CC0 (Wikidata)",
        source_url=f"https://www.wikidata.org/wiki/{qid}",
    )]

def record_to_drafts(source: str, payload: dict, lang: str | None = "en") -> list[CanonicalPoiDraft]:
    if source == "opentripmap":
        return opentripmap_to_drafts(payload, lang or "en")
    if source == "osm":
        return overpass_to_drafts(payload, lang or "en")
    if source == "wikidata":
        return wikidata_to_drafts(payload, lang or "en")
    raise ValueError(f"no mapper for source '{source}'")