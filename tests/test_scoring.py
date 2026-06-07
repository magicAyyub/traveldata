from traveldata.score import scorer, signals


def test_content_richness_monotonic_and_bounded():
    poor = signals.RichnessInputs(False, 0, 0, 1, False, 1)
    rich = signals.RichnessInputs(True, 800, 5, 4, True, 3)
    assert 0.0 <= signals.content_richness(poor) < signals.content_richness(rich) <= 1.0


def test_popularity_bounded_and_ignores_missing_signals():
    only_osm = signals.popularity(signals.PopularityInputs(osm_present=True))
    famous = signals.popularity(
        signals.PopularityInputs(pageviews_30d=200_000, sitelink_count=60, otm_rate=7, osm_present=True)
    )
    assert 0.0 <= only_osm <= 1.0
    assert famous > only_osm
    assert famous <= 1.0


def test_hidden_gem_requires_quality_floor():
    # No coords -> zero regardless of richness
    assert signals.hidden_gem_score(0.9, 0.1, has_coordinates=False,
                                    source_count=3, has_description=True) == 0.0
    # Single source, no description -> floor fails -> zero
    assert signals.hidden_gem_score(0.9, 0.1, has_coordinates=True,
                                    source_count=1, has_description=False) == 0.0
    # Rich + unpopular + passes floor -> high
    gem = signals.hidden_gem_score(0.9, 0.1, has_coordinates=True,
                                   source_count=2, has_description=True)
    assert gem > 0.4


def test_hidden_gem_penalizes_popularity():
    rich = 0.8
    obscure = signals.hidden_gem_score(rich, 0.1, has_coordinates=True,
                                       source_count=2, has_description=True)
    famous = signals.hidden_gem_score(rich, 0.95, has_coordinates=True,
                                      source_count=2, has_description=True)
    assert obscure > famous


def test_scorer_end_to_end_for_offbeat_museum():
    f = scorer.PoiFeatures(
        categories=["museum"],
        has_coordinates=True,
        description_len=120,
        image_count=1,
        source_count=2,
        lang_count=2,
        has_practical_info=True,
        pageviews_30d=800,        # low -> obscure
        sitelink_count=3,
        osm_present=True,
        offbeat_boost=True,
    )
    s = scorer.score(f)
    assert s.model_version == "heuristic-v1"
    assert 0.0 <= s.popularity <= 1.0
    assert s.hidden_gem_score > 0.2          # interesting but not famous
    assert s.activity_score == 0.4           # museum prior, no boosts
    assert "categories" in s.components


def test_non_destination_poi_scores_zero_hidden_gem():
    f = scorer.PoiFeatures(
        categories=["historic", "monument"], has_coordinates=True,
        description_len=200, source_count=2, lang_count=3,
        pageviews_30d=50, is_destination=False,
    )
    s = scorer.score(f)
    assert s.hidden_gem_score == 0.0
    assert s.content_richness > 0.0
