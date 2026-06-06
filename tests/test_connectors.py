"""Prove the connector fetch->RawDoc->draft path works without hitting any live API,
using httpx.MockTransport. Also smoke-imports models so schema stays import-clean.
"""
import json
from pathlib import Path

import httpx

from traveldata.cache.http_cache import RateLimitedClient
from traveldata.connectors.opentripmap import OpenTripMapConnector
from traveldata.connectors.osm_overpass import OverpassConnector, build_query

FIX = Path(__file__).parent / "fixtures"


def test_opentripmap_fetch_with_mock_transport():
    eiffel = json.loads((FIX / "otm_eiffel.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if "radius" in request.url.path:
            return httpx.Response(200, json=[{"xid": "W12345"}])
        if "xid/" in request.url.path:
            return httpx.Response(200, json=eiffel)
        return httpx.Response(404)

    client = RateLimitedClient(httpx.Client(transport=httpx.MockTransport(handler)),
                               min_interval_s=0.0)
    conn = OpenTripMapConnector(client=client, lang="en")

    drafts = []
    for unit in conn.discover(48.8584, 2.2945, radius_m=1000):
        for raw in conn.fetch(unit):
            assert raw.source == "opentripmap"
            assert raw.hash  # content hash computed
            drafts += conn.to_drafts(raw)
    assert len(drafts) == 1
    assert drafts[0].canonical_name == "Eiffel Tower"


def test_overpass_fetch_with_mock_transport():
    museum = json.loads((FIX / "osm_museum.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"elements": [museum]})

    client = RateLimitedClient(httpx.Client(transport=httpx.MockTransport(handler)),
                               min_interval_s=0.0)
    conn = OverpassConnector(client=client, lang="en")

    drafts = []
    for unit in conn.discover(48.86, 2.33, radius_m=1000):
        for raw in conn.fetch(unit):
            drafts += conn.to_drafts(raw)
    assert len(drafts) == 1
    assert drafts[0].source_id == "node/98765"


def test_overpass_query_builder_contains_selectors_and_bbox():
    q = build_query((48.8, 2.3, 48.9, 2.4))
    assert "[out:json]" in q and "out center tags;" in q
    assert "(48.8,2.3,48.9,2.4)" in q
    assert '"tourism"' in q


def test_models_import_clean():
    # Importing ORM must not require a DB driver or live connection.
    from traveldata.db import models
    assert models.Poi.__tablename__ == "poi"
    assert models.SourceRecord.__tablename__ == "source_record"
