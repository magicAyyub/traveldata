"""Map contributing sources to user-facing attribution strings (provenance surfaced)."""
from __future__ import annotations

_ATTR = {
    "osm": "© OpenStreetMap contributors (ODbL)",
    "wikidata": "Wikidata (CC0)",
    "opentripmap": "OpenTripMap (aggregated OSM/Wikidata/Wikipedia)",
    "wikivoyage": "Wikivoyage (CC BY-SA)",
}


def attributions(sources) -> list[str]:
    return [_ATTR.get(s, s) for s in sorted(sources or [])]