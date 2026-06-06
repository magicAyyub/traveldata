import json
from pathlib import Path

from traveldata.normalize import mappers

FIX = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIX / name).read_text())


def test_opentripmap_mapper_extracts_core_fields():
    drafts = mappers.opentripmap_to_drafts(_load("otm_eiffel.json"), lang="en")
    assert len(drafts) == 1
    d = drafts[0]
    assert d.source == "opentripmap"
    assert d.canonical_name == "Eiffel Tower"
    assert d.wikidata_qid == "Q243"
    assert (d.lat, d.lon) == (48.8584, 2.2945)
    assert d.importance_raw == 7.0
    assert d.heritage is True
    # xid 'W12345' should resolve to an OSM way reference
    assert d.source_xids["osm"] == "way/12345"
    assert d.source_xids["wikidata"] == "Q243"
    assert "architecture" in d.categories and "viewpoint" in d.categories
    assert d.descriptions["en"].startswith("The Eiffel Tower")
    assert len(d.images) == 2


def test_opentripmap_mapper_drops_records_without_name_or_coords():
    assert mappers.opentripmap_to_drafts({"xid": "X1", "point": {"lat": 1, "lon": 2}}) == []
    assert mappers.opentripmap_to_drafts({"name": "x", "point": {}}) == []


def test_overpass_mapper_extracts_multilingual_names_and_tags():
    drafts = mappers.overpass_to_drafts(_load("osm_museum.json"), lang="en")
    assert len(drafts) == 1
    d = drafts[0]
    assert d.source == "osm"
    assert d.source_id == "node/98765"
    assert d.wikidata_qid == "Q3330187"
    assert d.names["en"] == "Museum of Hunting and Nature"
    assert "fr" not in d.names  # only name:en present besides base name
    assert "museum" in d.categories
    assert d.source_url.endswith("node/98765")


def test_rate_parser_handles_plain_and_heritage():
    assert mappers._parse_otm_rate("3") == (3.0, False)
    assert mappers._parse_otm_rate("7h") == (7.0, True)
    assert mappers._parse_otm_rate(None) == (None, False)
