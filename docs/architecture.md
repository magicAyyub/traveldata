# traveldata

A free, **open-data-first** travel POI data layer. It ingests points of interest from
multiple open sources, resolves duplicates across them into single canonical records,
enriches them, scores them for **discovery** ("hidden gems", "good activities",
"popularity"), and serves the result over a spatial HTTP API.

It is **not** a booking system. It is the data foundation that later powers
recommendation, ranking, and agentic workflows.

Design constraints honored throughout: no paid APIs in the core path, no dependence on
any single source, provenance preserved for every record, multilingual content where
available, and a schema robust enough for a future recommender.

---

## 1. Architecture

A medallion-style multi-source ETL landing on Postgres + PostGIS, served by FastAPI.

```mermaid
flowchart LR
    subgraph Sources
        OSM[OpenStreetMap / Overpass]
        OTM[OpenTripMap]
        WD[Wikidata SPARQL]
        PV[Wikipedia pageviews]
    end

    subgraph Ingest
        CONN[Connectors] --> RAW[(source_record\nraw JSONB + provenance)]
    end

    OSM --> CONN
    OTM --> CONN

    RAW --> NORM[normalize\nmappers + taxonomy]
    NORM --> RES{entity resolution}
    RES -->|QID / spatial+name| CONF[conflate\nfield-level merge]
    CONF --> POI[(poi\ncanonical)]

    WD --> ENR[enrich]
    PV --> ENR
    ENR --> POI
    ENR -.metrics in payload.-> RAW

    POI --> SCORE[score\nheuristic-v1]
    SCORE --> SC[(poi_score)]

    POI --> API[FastAPI\n/pois/nearby, /pois/id]
    SC --> API
```

Layer responsibilities:

| Layer | Module(s) | Responsibility |
|---|---|---|
| Connectors | `connectors/` | Per-source I/O: discover, fetch, rate-limit, provenance |
| Raw store | `raw/store.py` | Idempotent landing of verbatim payloads into `source_record` |
| Normalize | `normalize/` | Pure source→canonical mappers + one category taxonomy |
| Resolve | `resolve/`, `pipeline/resolve.py` | Cluster source records into one canonical POI |
| Conflate | `resolve/conflate.py` | Field-level merge with recorded provenance |
| Enrich | `enrich/`, `pipeline/enrich.py` | Wikidata content/metrics + Wikipedia pageviews |
| Score | `score/`, `pipeline/scoring.py` | Interpretable component signals → versioned scores |
| Serve | `api/` | Spatial HTTP API over the canonical + score tables |

Storage stack: **Postgres 16 + PostGIS** (geography), **JSONB** (raw + flexible fields),
with **pgvector** reserved for description embeddings when the recommender lands.

### Package layout

```
traveldata/
  config.py                 # pydantic-settings; all endpoints/limits via env
  db/
    base.py                 # declarative Base + lazy engine/session factories
    models.py               # Place, Poi, SourceRecord, PoiLink, PoiScore
    migrations/             # alembic (0001 schema, 0002 enrichment, 0003 is_destination)
  connectors/
    base.py                 # Connector ABC + WorkUnit / RawDoc / CanonicalPoiDraft
    opentripmap.py          # primary POI source (geoname/radius/xid)
    osm_overpass.py         # OSM fallback + tag richness
  raw/store.py              # land_raw(): content-hash idempotent upsert
  normalize/
    mappers.py              # *_to_drafts(); record_to_drafts() dispatch
    taxonomy.py             # unified categories, activity priors, destination gate
  resolve/
    blocking.py             # geohash helpers
    matcher.py              # name normalization + rapidfuzz similarity
    conflate.py             # per-field priority merge -> ConflatedPoi
  enrich/
    wikidata.py             # batched SPARQL: labels, sitelinks, image, enwiki title, P31
    pageviews.py            # Wikimedia REST 30-day views
  score/
    signals.py              # content_richness, popularity, activity, hidden_gem
    scorer.py               # PoiFeatures -> PoiScoreResult (model_version)
  pipeline/
    ingest.py               # run_ingest(): fetch -> land raw
    resolve.py              # run_resolve(): match/create/link
    scoring.py              # reconflate_and_score(): shared conflate + score
    enrich.py               # run_enrich()
    cli.py                  # typer: sources/ingest/stats/resolve/enrich/pipeline/top/serve
  api/
    main.py                 # FastAPI app factory + module-level `app`
    deps.py                 # request-scoped DB session
    schemas.py              # PoiOut / PoiDetailOut / ScoreOut
    attributions.py         # source -> attribution string
    routers/pois.py         # /pois/nearby, /pois/{id}
  cache/http_cache.py       # RateLimitedClient (throttle + retry around httpx)
```

---

## 2. Data sources

| Source | License | Access | Contributes | Status |
|---|---|---|---|---|
| **OpenStreetMap** (Overpass) | ODbL | Overpass QL over bbox | POI inventory, tags (`opening_hours`, `tourism`, `historic`, `leisure`...), coordinates, QID xrefs | active |
| **OpenTripMap** | aggregated (ODbL/CC-BY-SA) | REST (`radius`, `xid`) | Wikipedia-extract descriptions, images, `rate` (importance), `kinds`, QID xrefs | active |
| **Wikidata** | CC0 | SPARQL (batched) | golden QID join key, multilingual labels/descriptions, `sitelinks`, `P18` image, `P31` instance-of, enwiki title | active (enrich) |
| **Wikipedia pageviews** | Wikimedia REST | per-article daily | 30-day views (popularity signal) | active (enrich) |
| **Atlas Obscura** | proprietary | N/A | offbeat inspiration | **excluded** (ToS bars scraping; use a curated name seed only) |
| **Wikivoyage** | CC BY-SA | dumps / MediaWiki API | `place` layer, practical info, "Do" content | planned |

Provenance is preserved on every `source_record` (`source`, `source_url`, `license`,
`content_hash`), and surfaced to API clients as `attributions`.

---

## 3. Data model

```mermaid
erDiagram
    PLACE ||--o{ POI : contains
    POI ||--o{ SOURCE_RECORD : "sourced from"
    POI ||--o{ POI_LINK : groups
    SOURCE_RECORD ||--o{ POI_LINK : member
    POI ||--o{ POI_SCORE : scored

    POI {
        uuid id PK
        text wikidata_qid "join key, indexed"
        text canonical_name
        jsonb names "lang -> name"
        geography geom "Point 4326"
        text geohash
        text[] categories "unified taxonomy"
        text[] raw_kinds
        text short_description
        jsonb descriptions "lang -> text"
        jsonb images
        jsonb source_xids "osm/wikidata/opentripmap ids"
        jsonb field_provenance "field -> winning source"
        int pageviews_30d
        int sitelink_count
        text wikipedia_title
        bool is_destination
        timestamp enriched_at
    }
    SOURCE_RECORD {
        uuid id PK
        uuid poi_id FK
        text source
        text source_id
        text lang
        jsonb payload "verbatim"
        text license
        text source_url
        text content_hash
    }
    POI_LINK {
        uuid poi_id FK
        uuid source_record_id FK
        text match_method "wikidata_qid|spatial_name|new"
        float match_score
    }
    POI_SCORE {
        uuid poi_id FK
        text model_version PK
        float popularity
        float content_richness
        float activity_score
        float hidden_gem_score
        jsonb components "raw signals for future LTR"
    }
    PLACE {
        uuid id PK
        text level "country|region|city|district"
        text canonical_name
        geography geom
        jsonb practical_info
        text wikivoyage_title
    }
```

Two deliberate choices:

- **`field_provenance`** records which source won each conflated field, so any value
  traces back (e.g. `{"geom":"osm","short_description":"opentripmap"}`).
- **`poi_score.components`** stores raw signal values, so a learning-to-rank model can
  later train on the exact features the heuristic used without requiring a schema change.

`PLACE` exists but is unpopulated until the Wikivoyage layer lands; today every POI has
`place_id = NULL` and discovery is geo-scoped.

Migrations: `0001_initial` (schema + PostGIS), `0002_enrichment` (`pageviews_30d`,
`sitelink_count`, `wikipedia_title`, `enriched_at`), `0003_destination_flag`
(`is_destination`).

---

## 4. Pipeline

The canonical order is **ingest → resolve → enrich**. The `pipeline` command runs
`resolve` then `enrich` together, which is what keeps scores and flags consistent after
any new ingest.

```mermaid
sequenceDiagram
    participant CLI
    participant CONN as Connector
    participant DB as Postgres
    participant WD as Wikidata/Pageviews

    CLI->>CONN: ingest(lat, lon, radius)
    CONN->>CONN: discover() -> WorkUnit(s)
    loop each POI
        CONN->>DB: land_raw(RawDoc)  [content-hash skip if unchanged]
    end

    CLI->>DB: resolve()
    loop each unresolved source_record
        DB->>DB: record_to_drafts()
        alt QID match
            DB->>DB: link to existing POI
        else spatial + name match (<=80m, sim>=0.85)
            DB->>DB: link to nearby POI
        else
            DB->>DB: create new POI
        end
        DB->>DB: reconflate_and_score()
    end

    CLI->>DB: enrich()  [POIs with QID, not yet enriched]
    DB->>WD: SPARQL batch (labels, sitelinks, P18, P31, enwiki)
    DB->>WD: pageviews per enwiki title
    WD-->>DB: info
    DB->>DB: land wikidata source_record + link + reconflate_and_score()
```

Operational properties:

- **Idempotent ingest**: `land_raw` keys on `(source, source_id, lang)` and skips
  unchanged payloads via `content_hash`. Re-running an ingest is cheap and safe.
- **Rebuild-safe enrichment**: Wikidata metrics (`sitelinks`, `pageviews_30d`,
  `instance_of`, `enwiki_title`) live inside the Wikidata `source_record` *payload*, not
  only on `poi`. So `resolve --rebuild` restores everything from stored payloads with
  **no network calls**. You only pay the Wikidata/pageviews cost on first enrich (or an
  explicit `enrich --refresh`).
- **Crash-safe ingest**: `run_ingest` commits every 100 records; a mid-run failure
  keeps progress, and idempotency lets a re-run resume.

---

## 5. Entity resolution & conflation

For each unresolved `source_record`, map it to a `CanonicalPoiDraft`, then match:

```mermaid
flowchart TD
    A[source_record] --> B[record_to_drafts]
    B --> C{wikidata_qid set\nand matches a POI?}
    C -->|yes| M[link: wikidata_qid]
    C -->|no| D{POI within 80 m\nand name sim >= 0.85?}
    D -->|yes| N[link: spatial_name]
    D -->|no| E[create new POI]
    M --> R[reconflate_and_score]
    N --> R
    E --> R
```

- **QID exact match** is the golden path: OSM tags and OTM both carry `wikidata` ids, so
  the same real place across sources collapses for free.
- **Spatial + name** fallback blocks candidates with PostGIS `ST_DWithin` (≤ 80 m) and
  scores names with `rapidfuzz.token_sort_ratio` on accent-stripped, normalized strings
  (threshold 0.85). Both are tunable per run.

**Conflation** chooses each field by per-field source priority (recorded in
`field_provenance`):

| Field | Priority (highest → lowest) | Rationale |
|---|---|---|
| `geom` | osm → wikidata → opentripmap | OSM/Wikidata coordinates are most authoritative |
| name / `names` | wikidata → osm → wikivoyage → opentripmap | clean multilingual labels |
| description | wikivoyage → opentripmap → osm → wikidata | richest prose wins |
| `categories`, `raw_kinds`, `images`, `source_xids` | union / merge | N/A |
| `importance_raw` (rate) | OpenTripMap only | only OTM provides it |

`canonical_name` is taken from merged `names` in the default language when present.

---

## 6. Scoring (`model_version = heuristic-v1`)

Every signal is interpretable and normalized to `[0, 1]`; raw inputs are persisted in
`poi_score.components` so a learned ranker can replace the heuristic without re-plumbing.

```mermaid
flowchart LR
    subgraph inputs
        D[desc length]
        I[image count]
        S[source count]
        L[lang count]
        P[has practical info]
        PV[pageviews_30d]
        SL[sitelink_count]
        R[otm rate]
        CAT[categories]
        DEST[is_destination]
    end

    D & I & S & L & P --> CR[content_richness]
    PV & SL & R --> POP[popularity]
    CAT --> ACT[activity_score]
    CR & POP & DEST --> GEM[hidden_gem_score]
```

**content_richness** (documentation depth):

```
0.20 · has_description
+ 0.20 · min(description_len / 1500, 1)     # full description, not the truncated summary
+ 0.15 · min(image_count / 3, 1)
+ 0.20 · min(source_count / 4, 1)
+ 0.15 · has_practical_info                  # OSM opening_hours/website/phone/fee or OTM address/url
+ 0.10 · min(lang_count / 3, 1)
```

**popularity**: weighted mean over the *evidence* present (missing signals drop out).
OSM presence is only a weak prior:

```
pageviews:  min(log10(views + 1) / 5, 1)   weight 0.55
sitelinks:  min(sitelinks / 40, 1)         weight 0.30
otm_rate:   (rate - 1) / 6                  weight 0.15
+ 0.05 nudge if present in OSM
fallback: 0.10 if only OSM presence, else 0.0
```

**activity_score**: a per-category prior (things you *do* score higher than things you
look at), boosted by Wikivoyage "Do" membership and OSM leisure/sport tags:

```
clamp( activity_prior(categories) + 0.30·in_wikivoyage_do + 0.20·osm_leisure_sport )
```

Priors (excerpt): `hiking 0.95, water_activity 0.90, sport 0.90, amusement 0.85,
market 0.70, viewpoint 0.60, park 0.60, food 0.55, art 0.45, museum 0.40,
historic 0.30, monument 0.25, water_body 0.25, public_art 0.10, other 0.20`.

**hidden_gem_score**: interesting but not famous, gated so junk and non-destinations
can't win:

```
quality_floor = has_coordinates AND (has_description OR source_count >= 2)
hidden_gem = (is_destination AND quality_floor)
             ? content_richness · (1 - popularity) · (0.6 + 0.4·offbeat_boost)
             : 0
```

**`is_destination`**: the discrete-artwork / non-place gate:

```mermaid
flowchart TD
    A[POI] --> B{"public_art in categories?\n(OSM tourism=artwork)"}
    B -->|yes| X[NOT a destination]
    B -->|no| C{"Wikidata P31 in\nNON_DESTINATION_INSTANCES?\n(sculpture, statue, bust, monument, ...)"}
    C -->|yes| X
    C -->|no| D{has any real category?}
    D -->|yes| Y[destination]
    D -->|no| X
```

This keeps individual statues, busts, and plaques out of the destination/gem surfaces.
It is gated only on `hidden_gem_score` and the API's `destinations_only` filter;
`content_richness` and `popularity` remain raw component signals.

---

## 7. HTTP API

FastAPI over PostGIS. Run with `traveldata serve` (or `uvicorn traveldata.api.main:app`);
interactive docs at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /pois/nearby` | spatial discovery (`ST_DWithin`) ordered by a score |
| `GET /pois/{id}` | full POI detail with descriptions + attributions |

`/pois/nearby` parameters: `lat`, `lon`, `radius_m` (1–50000), `categories`
(comma-separated, matches any), `min_hidden_gem`, `sort`
(`hidden_gem_score`|`activity_score`|`popularity`|`content_richness`|`distance`),
`destinations_only` (default `true`), `limit`.

Example:

```bash
curl "http://127.0.0.1:8000/pois/nearby?lat=48.8606&lon=2.3376&radius_m=1500&sort=hidden_gem_score&limit=10"
```

Each result includes its scores, `field_provenance`, and `attributions` assembled from
the real contributing sources, making responses license-compliant by construction.

---

## 8. CLI

```
traveldata sources                 # list connectors + licenses
traveldata ingest --source osm|opentripmap --lat .. --lon .. --radius-m ..
traveldata stats                   # source_record counts by source
traveldata resolve [--rebuild]     # match/create/link/conflate/score
traveldata enrich [--refresh] [--no-pageviews]
traveldata pipeline [--rebuild]    # resolve then enrich (recommended after an ingest)
traveldata top --metric <m> [--limit N]
traveldata serve [--host --port --reload]
```

`--rebuild` wipes `poi`/`poi_link`/`poi_score`, nulls `source_record.poi_id`, and
re-resolves from raw, restoring enrichment from payloads with no network.

---

## 9. Configuration

All settings are overridable via `TRAVELDATA_<UPPER>` env vars or a `.env` file.

| Variable | Default / note |
|---|---|
| `TRAVELDATA_DATABASE_URL` | `postgresql+psycopg://...` (PostGIS required) |
| `TRAVELDATA_OPENTRIPMAP_API_KEY` | required for OTM ingest |
| `TRAVELDATA_OVERPASS_URL` | `https://overpass-api.de/api/interpreter` |
| `TRAVELDATA_WIKIDATA_SPARQL_URL` | `https://query.wikidata.org/sparql` |
| `TRAVELDATA_DEFAULT_LANG` | `en` |
| `TRAVELDATA_HTTP_MIN_INTERVAL_S` | per-connector politeness throttle |
| `TRAVELDATA_USER_AGENT` | set a real contact string (WDQS/Wikimedia require it) |

---

## 10. Running locally

```bash
# 1. PostGIS (dev). Swap DATABASE_URL for Neon etc. in prod, same migrations.
docker run -d --name traveldata \
  -e POSTGRES_PASSWORD=traveldata -e POSTGRES_DB=traveldata \
  -p 5433:5432 postgis/postgis:16-3.4

# 2. Config
echo 'TRAVELDATA_DATABASE_URL=postgresql+psycopg://postgres:traveldata@localhost:5433/traveldata' >> .env
echo 'TRAVELDATA_OPENTRIPMAP_API_KEY=...' >> .env
echo 'TRAVELDATA_USER_AGENT=traveldata/0.1 (you@example.com)' >> .env

# 3. Install + schema
uv sync                       # or: uv pip install -e ".[dev,serve]"
uv run alembic upgrade head

# 4. Build a city
uv run traveldata ingest --source osm         --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata ingest --source opentripmap --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata pipeline                     # resolve + enrich

# 5. Serve
uv run traveldata serve --reload
```

---

## 11. Licensing & compliance

- **Wikidata**: CC0 (no attribution required); the join layer.
- **OSM**: ODbL: attribution ("© OpenStreetMap contributors") + share-alike.
- **OpenTripMap**: aggregates OSM/Wikidata/Wikipedia; inherit those licenses, carry
  attribution downstream, respect API ToS and rate limits.
- **Wikipedia extracts / Wikivoyage**: CC BY-SA: attribution + share-alike.
- **Atlas Obscura**: proprietary; **not** scraped or stored. Only a hand-curated list of
  place *names* (facts) may be used, then re-resolved through the open sources.

Every record keeps `license` + `source_url`; the API exposes `attributions`.

---

## 12. Known limitations & tuning knobs

- **Non-destination filtering** is a hand-curated `P31` blocklist plus the `public_art`
  rule. Artworks have a long tail of instance types; the principled fix is a one-time
  Wikidata `P279` (subclass-of) walk up to "work of art" (Q838948), cached per QID.
- **`public_art` is a hard exclusion**, so famous public art (e.g. the Buren Columns) is
  also dropped from destinations. To keep notable ones, thread `sitelink_count` into
  `is_destination` and keep `public_art` when sitelinks are high.
- **`content_richness` / `popularity` are not gated** by `is_destination` (by design,
  as they are raw component signals). Add an `is_destination` filter to `top` or the API if you
  want them suppressed everywhere.
- **Discovery is single-bbox** per ingest (no tiling) and **resolution is per-record**
  (not batch-optimized), which works fine at city scale but should be revisited for country-scale loads.
- **`place` table is empty**: discovery is geo-scoped until the Wikivoyage layer lands.

---

## 13. Roadmap

1. **Wikivoyage layer**: populate `place` (cities/districts + practical info), enabling
   `/places/{id}/highlights`; feed "Do" sections into `activity_score`; a second rich
   content source flowing through conflation.
2. **P279 instance classification**: replace the hand-curated artwork blocklist.
3. **Recommender**: sentence-transformer description embeddings into `pgvector` for
   "more like this"; train LTR on `poi_score.components` once engagement data exists.
4. **More connectors**: the `Connector` ABC makes additional open sources pluggable.
