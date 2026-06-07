"""Parse Wikivoyage wikitext into a place (prose + practical info) and POI listings."""
from __future__ import annotations

from dataclasses import dataclass, field

import mwparserfromhell

_LISTING_TEMPLATES = {"see", "do", "buy", "eat", "drink", "sleep", "listing", "vcard"}
_SKIP_KINDS = {"sleep"}  # accommodation isn't a discovery POI
_DESC_SECTIONS = {"understand"}
_PRACTICAL_SECTIONS = {"get in", "get around", "stay safe", "stay healthy", "connect", "cope"}


@dataclass
class Listing:
    kind: str
    name: str
    lat: float | None = None
    lon: float | None = None
    address: str | None = None
    hours: str | None = None
    price: str | None = None
    phone: str | None = None
    url: str | None = None
    content: str | None = None
    wikidata: str | None = None


@dataclass
class ParsedPlace:
    descriptions: dict[str, str] = field(default_factory=dict)
    practical_info: dict[str, str] = field(default_factory=dict)
    listings: list[Listing] = field(default_factory=list)
    center: tuple[float, float] | None = None


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _p(t, name):
    if t.has(name):
        v = t.get(name).value.strip_code().strip()
        return v or None
    return None


def _section_heading(section):
    hs = section.filter_headings()
    return str(hs[0].title).strip() if hs else None


def _section_text(section) -> str:
    sc = mwparserfromhell.parse(str(section))
    for h in sc.filter_headings():
        sc.remove(h)
    for link in sc.filter_wikilinks():
        if str(link.title).lower().startswith(("file:", "image:", "category:")):
            sc.remove(link)
    return sc.strip_code().strip()


def parse_page(wikitext: str, lang: str = "en") -> ParsedPlace:
    code = mwparserfromhell.parse(wikitext)

    listings: list[Listing] = []
    for t in code.filter_templates():
        tname = str(t.name).strip().lower()
        if tname not in _LISTING_TEMPLATES:
            continue
        kind = (_p(t, "type") or "see") if tname in {"listing", "vcard"} else tname
        kind = (kind or "see").lower()
        if kind in _SKIP_KINDS:
            continue
        name = _p(t, "name")
        if not name:
            continue
        listings.append(Listing(
            kind=kind, name=name,
            lat=_to_float(_p(t, "lat")), lon=_to_float(_p(t, "long") or _p(t, "lng")),
            address=_p(t, "address"), hours=_p(t, "hours"), price=_p(t, "price"),
            phone=_p(t, "phone"), url=_p(t, "url"),
            content=_p(t, "content"), wikidata=_p(t, "wikidata"),
        ))

    descriptions, practical, desc_parts = {}, {}, []
    for section in code.get_sections(levels=[2], include_lead=True, include_headings=True):
        heading = _section_heading(section)
        text = _section_text(section)
        if not text:
            continue
        if heading is None or heading.lower() in _DESC_SECTIONS:
            desc_parts.append(text)
        elif heading.lower() in _PRACTICAL_SECTIONS:
            practical[heading.lower().replace(" ", "_")] = text[:1500]
    if desc_parts:
        descriptions[lang] = "\n\n".join(desc_parts)[:2000]

    coords = [(l.lat, l.lon) for l in listings if l.lat is not None and l.lon is not None]
    center = (sum(a for a, _ in coords) / len(coords),
              sum(b for _, b in coords) / len(coords)) if coords else None

    return ParsedPlace(descriptions=descriptions, practical_info=practical,
                       listings=listings, center=center)