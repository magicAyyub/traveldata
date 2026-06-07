from traveldata.normalize.mappers import wikivoyage_listing_to_draft
from traveldata.normalize.wikivoyage_parse import parse_page

WIKITEXT = """'''Paris/1st arrondissement''' is the heart of Paris.

==Understand==
The 1st arrondissement contains the Louvre and the Tuileries.

==See==
{{see
| name=Louvre | lat=48.8606 | long=2.3376 | wikidata=Q19675
| hours=9:00-18:00 | price=Euro 17
| content=The world's largest art museum.
}}

==Do==
{{do | name=Tuileries Garden | lat=48.8635 | long=2.3275
| content=Stroll through the historic royal garden. }}

==Sleep==
{{sleep | name=Hotel Costes | lat=48.868 | long=2.327 }}

==Get in==
The arrondissement is served by several metro lines.
"""


def test_parse_page_extracts_listings_sections_center():
    p = parse_page(WIKITEXT, "en")
    names = {l.name: l for l in p.listings}
    assert "Louvre" in names and "Tuileries Garden" in names
    assert "Hotel Costes" not in names               # sleep is skipped
    assert names["Louvre"].kind == "see"
    assert names["Louvre"].wikidata == "Q19675"
    assert names["Louvre"].hours == "9:00-18:00"
    assert names["Tuileries Garden"].kind == "do"
    assert "Louvre and the Tuileries" in p.descriptions["en"]
    assert "get_in" in p.practical_info
    assert p.center is not None and 48.86 < p.center[0] < 48.87


def test_wikivoyage_mapper_marks_do_kind():
    d = wikivoyage_listing_to_draft(
        {"name": "Tuileries Garden", "lat": 48.8635, "lon": 2.3275, "kind": "do",
         "content": "Stroll the royal garden.", "source_id": "x#do:Tuileries Garden"}, "en")[0]
    assert d.source == "wikivoyage"
    assert d.categories == ["other"]
    assert d.short_description.startswith("Stroll")