from traveldata.connectors.base import CanonicalPoiDraft
from traveldata.resolve.conflate import conflate
from traveldata.resolve.matcher import name_similarity


def test_name_similarity_handles_accents_and_word_order():
    assert name_similarity("Musée du Louvre", "Musee du Louvre") > 0.95
    assert name_similarity("Tour Eiffel", "Eiffel Tour") > 0.95
    assert name_similarity("Eiffel Tower", "Notre Dame Cathedral") < 0.5


def _otm():
    return CanonicalPoiDraft(
        source="opentripmap", source_id="W1", canonical_name="Eiffel Tower",
        lat=48.8584, lon=2.2945, names={"en": "Eiffel Tower"}, wikidata_qid="Q243",
        categories=["architecture", "viewpoint"], short_description="A wrought-iron tower.",
        importance_raw=7.0, heritage=True,
        source_xids={"opentripmap": "W1", "wikidata": "Q243"},
    )


def _osm():
    return CanonicalPoiDraft(
        source="osm", source_id="way/5013364", canonical_name="Tour Eiffel",
        lat=48.8585, lon=2.2944, names={"en": "Eiffel Tower", "fr": "Tour Eiffel"},
        wikidata_qid="Q243", categories=["viewpoint"], short_description=None,
        source_xids={"osm": "way/5013364", "wikidata": "Q243"},
    )


def test_conflate_applies_field_priorities_and_merges():
    c = conflate([_otm(), _osm()])
    # geom: OSM wins over OpenTripMap
    assert (c.lat, c.lon) == (48.8585, 2.2944)
    assert c.field_provenance["geom"] == "osm"
    # canonical name from default-lang merged names
    assert c.canonical_name == "Eiffel Tower"
    assert c.names["fr"] == "Tour Eiffel"
    # description: only OTM had one -> OTM wins
    assert c.short_description.startswith("A wrought-iron")
    assert c.field_provenance["short_description"] == "opentripmap"
    # categories unioned; importance kept from OTM; both sources recorded
    assert {"architecture", "viewpoint"} <= set(c.categories)
    assert c.importance_raw == 7.0 and c.heritage is True
    assert c.sources == ["opentripmap", "osm"]
    assert c.source_xids["osm"] == "way/5013364"