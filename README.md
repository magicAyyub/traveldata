# traveldata

Free, open-data-first travel POI data layer. Multi-source ingestion → canonical
POI/destination store → ranking (hidden-gem / activity) → FastAPI serving.

## What's built in this slice

End-to-end **fetch → map → score** spine, proven by unit tests, plus the schema.

- `connectors/` — `Connector` ABC + two interchangeable sources: **OpenTripMap**
  (primary) and **OSM/Overpass** (fallback). I/O is isolated; mapping is pure.
- `normalize/` — `taxonomy.py` (one category vocabulary for every source) and
  `mappers.py` (source payload → `CanonicalPoiDraft`, fully unit-tested).
- `score/` — interpretable signals (`content_richness`, `popularity`,
  `activity_score`, `hidden_gem_score`) → versioned `PoiScoreResult`.
- `db/models.py` — SQLAlchemy 2.0 ORM matching the normalized schema (PostGIS).
- `raw/store.py` — idempotent landing into `source_record` (content-hash skip).
- `pipeline/cli.py` — `traveldata ingest|sources|...` (ingest is a live dry-run).
- `api/main.py` — FastAPI surface (health now; spatial endpoints next slice).

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                      # 17 passing
traveldata sources             # list connectors

# Live dry-run (needs network to api.opentripmap.com + a key in TRAVELDATA_OPENTRIPMAP_API_KEY)
traveldata ingest --source osm --lat 48.8606 --lon 2.3376 --radius-m 1500
```

Config via env (prefix `TRAVELDATA_`) — see `.env.example`.

## Not yet built (next slices, in order)

1. **Persistence**: Alembic migration + PostGIS DDL; wire `ingest` to `land_raw`.
2. **Entity resolution** (`resolve/`): QID exact-match → geohash+name blocking →
   conflation with `field_provenance`. (`pip install -e ".[resolve]"`)
3. **Wikivoyage connector** (`.[wikivoyage]`): dump parse + listing extraction for
   destination context and the `Do` sections that drive `activity_score`.
4. **Enrichment**: Wikidata SPARQL, Wikipedia extracts, pageviews, embeddings (pgvector).
5. **Serving**: PostGIS `ST_DWithin` nearby, highlights, search.

## Licensing / provenance

Every `source_record` carries `license` + `source_url`. OSM = ODbL (attribution +
share-alike); OpenTripMap aggregates OSM/Wikidata/Wikipedia (inherit those). Wikidata
= CC0. Wikivoyage/Wikipedia = CC BY-SA. **Atlas Obscura is intentionally excluded from
automated ingestion** (proprietary, ToS bars scraping) — use a curated name seed only.
