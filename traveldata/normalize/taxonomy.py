"""One category vocabulary that every source maps into.

`map_otm_kinds` and `map_osm_tags` are the only two entry points the connectors use.
ACTIVITY_PRIOR feeds the activity_score signal (things you *do* score higher than
things you merely look at).
"""
from __future__ import annotations

# --- Unified categories -----------------------------------------------------
# Keep this list small and stable; everything maps into it.
CATEGORIES = {
    "museum", "historic", "monument", "religious", "architecture", "cultural",
    "art", "natural", "viewpoint", "park", "beach", "water", "hiking",
    "sport", "amusement", "market", "food", "nightlife", "other",
}

# Activity-ness: 1.0 = an active thing to do, 0.0 = passive sightseeing.
ACTIVITY_PRIOR = {
    "hiking": 0.95, "water": 0.9, "sport": 0.9, "amusement": 0.85,
    "market": 0.7, "nightlife": 0.7, "viewpoint": 0.6, "park": 0.6,
    "beach": 0.6, "food": 0.55, "art": 0.45, "cultural": 0.45,
    "museum": 0.4, "religious": 0.3, "architecture": 0.3,
    "historic": 0.3, "monument": 0.25, "other": 0.2,
}

# --- OpenTripMap "kinds" (comma string) -> category -------------------------
_OTM_KIND_MAP = {
    "museums": "museum", "art_galleries": "art", "theatres_and_entertainments": "cultural",
    "urban_environment": "architecture", "historic_architecture": "architecture",
    "architecture": "architecture", "monuments_and_memorials": "monument",
    "monuments": "monument", "fortifications": "historic", "castles": "historic",
    "historic": "historic", "archaeology": "historic", "religion": "religious",
    "churches": "religious", "temples": "religious", "natural": "natural",
    "geological_formations": "natural", "water": "water", "beaches": "beach",
    "national_parks": "park", "nature_reserves": "park", "gardens_and_parks": "park",
    "view_points": "viewpoint", "towers": "viewpoint", "sport": "sport",
    "amusements": "amusement", "amusement_parks": "amusement", "marketplaces": "market",
    "foods": "food", "restaurants": "food", "nightclubs": "nightlife",
    "cultural": "cultural", "interesting_places": "other", "tourist_facilities": "other",
}


def map_otm_kinds(kinds: str | None) -> list[str]:
    if not kinds:
        return []
    out: list[str] = []
    for raw in kinds.split(","):
        cat = _OTM_KIND_MAP.get(raw.strip())
        if cat and cat not in out:
            out.append(cat)
    if not out:
        out = ["other"]
    return out


# --- OSM tags (dict) -> category --------------------------------------------
def map_osm_tags(tags: dict[str, str]) -> list[str]:
    out: list[str] = []

    def add(c: str) -> None:
        if c not in out:
            out.append(c)

    t = tags
    if t.get("tourism") in {"museum"}:
        add("museum")
    if t.get("tourism") in {"gallery"} or t.get("artwork_type"):
        add("art")
    if t.get("tourism") in {"viewpoint"}:
        add("viewpoint")
    if t.get("tourism") in {"theme_park"} or t.get("leisure") == "water_park":
        add("amusement")
    if t.get("historic"):
        add("historic")
    if t.get("historic") in {"monument", "memorial"}:
        add("monument")
    if t.get("building") in {"cathedral", "church", "mosque", "temple", "synagogue"} or t.get("amenity") == "place_of_worship":
        add("religious")
    if t.get("natural") in {"peak", "cave_entrance", "volcano", "cliff"}:
        add("natural")
    if t.get("natural") in {"beach"} or t.get("leisure") == "beach_resort":
        add("beach")
    if t.get("natural") in {"water", "spring", "hot_spring"} or t.get("waterway"):
        add("water")
    if t.get("leisure") in {"park", "garden", "nature_reserve"} or t.get("boundary") == "national_park":
        add("park")
    if t.get("sport") or t.get("leisure") in {"sports_centre", "pitch", "stadium"}:
        add("sport")
    if t.get("route") == "hiking" or t.get("highway") == "trailhead":
        add("hiking")
    if t.get("shop") == "marketplace" or t.get("amenity") == "marketplace":
        add("market")
    if t.get("amenity") in {"restaurant", "cafe", "food_court"}:
        add("food")
    if t.get("amenity") in {"nightclub", "bar", "pub"}:
        add("nightlife")
    if t.get("building") in {"tower"} or t.get("man_made") == "tower":
        add("viewpoint")
    if not out:
        add("other")
    return out


def activity_prior(categories: list[str]) -> float:
    if not categories:
        return ACTIVITY_PRIOR["other"]
    return max(ACTIVITY_PRIOR.get(c, ACTIVITY_PRIOR["other"]) for c in categories)
