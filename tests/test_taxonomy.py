from traveldata.normalize import taxonomy


def test_otm_kinds_map_to_unified_categories():
    cats = taxonomy.map_otm_kinds("towers,architecture,interesting_places,view_points,historic")
    assert "architecture" in cats
    assert "viewpoint" in cats
    assert "historic" in cats
    assert all(c in taxonomy.CATEGORIES for c in cats)


def test_otm_unknown_kinds_fall_back_to_other():
    assert taxonomy.map_otm_kinds("totally_made_up_kind") == ["other"]
    assert taxonomy.map_otm_kinds("") == []
    assert taxonomy.map_otm_kinds(None) == []


def test_osm_tags_map_museum_and_religious():
    assert "museum" in taxonomy.map_osm_tags({"tourism": "museum"})
    assert "religious" in taxonomy.map_osm_tags({"amenity": "place_of_worship"})
    assert taxonomy.map_osm_tags({"foo": "bar"}) == ["other"]


def test_activity_prior_prefers_active_categories():
    assert taxonomy.activity_prior(["hiking"]) > taxonomy.activity_prior(["monument"])
    assert taxonomy.activity_prior(["museum", "hiking"]) == taxonomy.activity_prior(["hiking"])
    assert 0.0 <= taxonomy.activity_prior([]) <= 1.0


def test_public_art_is_not_a_destination():
    from traveldata.normalize import taxonomy
    assert taxonomy.map_osm_tags({"tourism": "artwork", "artwork_type": "statue"}) == ["public_art"]
    assert taxonomy.map_osm_tags({"tourism": "gallery"}) == ["art"]
    assert taxonomy.is_destination(["public_art"]) is False
    assert taxonomy.is_destination(["public_art", "historic"]) is True
    assert taxonomy.is_destination(["museum"]) is True
    assert taxonomy.is_destination([]) is False
