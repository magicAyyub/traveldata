# traveldata

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Postgres](https://img.shields.io/badge/postgres-16%20%2B%20PostGIS-336791)
![API](https://img.shields.io/badge/api-FastAPI-009688)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC)
![Data](https://img.shields.io/badge/data-open--data--first-success)

A free, open-data-first travel **POI data layer**. It ingests points of interest from
multiple open sources (OpenStreetMap, OpenTripMap, Wikidata, Wikipedia pageviews),
resolves duplicates across them into single provenance-tracked records, enriches them,
and scores them for discovery (**hidden gems**, **good activities**, **popularity**)
behind a spatial HTTP API. Not a booking system; the data foundation for recommendation,
ranking, and agentic workflows.

## Why

- **Open-data-first**: no paid APIs in the core path.
- **Multi-source by design**: never depends on one provider; sources merge on the
  Wikidata QID, then fall back to spatial + name matching.
- **Provenance everywhere**: every record keeps its source, license, and which source
  won each field; API responses carry attributions.
- **Built for ranking**: interpretable, versioned scores with raw signals stored for a
  future learning-to-rank model.

## Quickstart

```bash
# PostGIS (dev): swap DATABASE_URL for Neon/RDS in prod, same migrations
docker run -d --name traveldata \
  -e POSTGRES_PASSWORD=traveldata -e POSTGRES_DB=traveldata \
  -p 5433:5432 postgis/postgis:16-3.4

cat >> .env <<'ENV'
TRAVELDATA_DATABASE_URL=postgresql+psycopg://postgres:traveldata@localhost:5433/traveldata
TRAVELDATA_OPENTRIPMAP_API_KEY=your_key_here
TRAVELDATA_USER_AGENT=traveldata/0.1 (you@example.com)
ENV

uv sync
uv run alembic upgrade head

# build a city, then resolve + enrich
uv run traveldata ingest --source osm         --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata ingest --source opentripmap --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata pipeline        # resolve then enrich

uv run traveldata serve --reload  # http://127.0.0.1:8000/docs
```

```bash
# top hidden gems near the Louvre, destinations only
curl "http://127.0.0.1:8000/pois/nearby?lat=48.8606&lon=2.3376&radius_m=1500&sort=hidden_gem_score&limit=10"
```

## CLI

```
traveldata sources | ingest | stats | resolve | enrich | pipeline | top | serve
```

`pipeline` runs `resolve` then `enrich`, which is the order to use after any new ingest.

## Documentation

Full design (architecture diagrams, schema, resolution/conflation, the scoring model,
API reference, and tuning knobs) lives in **[docs/architecture.md](docs/architecture.md)**.

## Licensing

Code under your chosen license. Data inherits its sources: OSM **ODbL**, Wikidata
**CC0**, Wikipedia/Wikivoyage **CC BY-SA**, OpenTripMap aggregated. Atlas Obscura is
deliberately **not** scraped. Attribution is surfaced on every API response.

## Status

Working three-source POI layer (OSM + OpenTripMap + Wikidata) with spatial serving.
Next: the **Wikivoyage layer** (destination/`place` data, practical info, "Do" content).
