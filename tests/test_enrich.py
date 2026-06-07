from traveldata.enrich.wikidata import parse_binding
from traveldata.normalize.mappers import wikidata_to_drafts


def test_parse_binding_decodes_labels_and_sitelinks():
    b = {
        "item": {"value": "http://www.wikidata.org/entity/Q243"},
        "sitelinks": {"value": "95"},
        "image": {"value": "http://commons.wikimedia.org/Special:FilePath/Eiffel.jpg"},
        "title": {"value": "Eiffel Tower"},
        "labels": {"value": "en|Eiffel Tower‖fr|Tour Eiffel"},
        "descs": {"value": "en|tower in Paris‖fr|tour à Paris"},
    }
    info = parse_binding(b)
    assert info.qid == "Q243"
    assert info.sitelink_count == 95
    assert info.labels["fr"] == "Tour Eiffel"
    assert info.descriptions["en"] == "tower in Paris"
    assert info.enwiki_title == "Eiffel Tower"


def test_wikidata_mapper_builds_multilingual_draft():
    d = wikidata_to_drafts({
        "qid": "Q243", "labels": {"en": "Eiffel Tower", "fr": "Tour Eiffel"},
        "descriptions": {"en": "iron tower"}, "image": "http://x/Eiffel.jpg",
        "point": {"lat": 48.8584, "lon": 2.2945},
    }, lang="en")[0]
    assert d.source == "wikidata" and d.wikidata_qid == "Q243"
    assert d.names["fr"] == "Tour Eiffel"
    assert d.short_description == "iron tower"
    assert len(d.images) == 1


def test_parse_binding_extracts_instance_of():
    b = {"item": {"value": "http://www.wikidata.org/entity/Q179700"},
         "instances": {"value": "Q179700|Q860861"}}
    assert "Q179700" in parse_binding(b).instance_of


def test_non_destination_instance_flags_statues():
    from traveldata.normalize import taxonomy
    assert taxonomy.non_destination_instance(["Q179700"]) is True      # statue
    assert taxonomy.non_destination_instance(["Q33506"]) is False      # museum