# traveldata

A free, **open-data-first** travel POI data layer. It ingests points of interest from
multiple open sources, resolves duplicates across them into single canonical records,
enriches them, scores them for **discovery** ("hidden gems", "good activities",
"popularity"), and serves the result over a spatial HTTP API at both **POI** and
**place** (city/area) levels.

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
        WV[Wikivoyage]
        WD[Wikidata SPARQL]
        PV[Wikipedia pageviews]
    end

    OSM --> CONN[Connectors]
    OTM --> CONN
    CONN --> RAW[(source_record\nraw JSONB + provenance)]

    WV --> PLI[ingest-place\nparse prose + listings]
    PLI --> PLACE[(place)]
    PLI --> RAW

    RAW --> NORM[normalize\nmappers + taxonomy]
    NORM --> RES{entity resolution}
    RES -->|QID / spatial+name| CONF[conflate\nfield-level merge]
    CONF --> POI[(poi)]

    WD --> ENR[enrich]
    PV --> ENR
    ENR --> POI
    ENR -.metrics in payload.-> RAW

    POI --> SCORE[score\nheuristic-v1]
    SCORE --> SC[(poi_score)]

    POI --> API[FastAPI\n/pois/*  /places/*]
    SC --> API
    PLACE --> API
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
| Places | `connectors/wikivoyage.py`, `normalize/wikivoyage_parse.py`, `pipeline/places.py` | Destination pages → `place` rows + POI listings |
| Score | `score/`, `pipeline/scoring.py` | Interpretable component signals → versioned scores |
| Serve | `api/` | Spatial HTTP API over the canonical + score + place tables |

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
    wikivoyage.py           # MediaWiki API: fetch destination-page wikitext
  raw/store.py              # land_raw(): content-hash idempotent upsert
  normalize/
    mappers.py              # *_to_drafts(); record_to_drafts() dispatch
    taxonomy.py             # unified categories, activity priors, destination gate
    wikivoyage_parse.py     # pure parser: wikitext -> place prose + listings
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
    resolve.py              # run_resolve(): match/create/link (+ place_id propagation)
    scoring.py              # reconflate_and_score(): shared conflate + score
    enrich.py               # run_enrich()
    places.py               # run_ingest_place(): Wikivoyage page -> place + listings
    cli.py                  # typer: sources/ingest/ingest-place/stats/resolve/enrich/pipeline/top/serve
  api/
    main.py                 # FastAPI app factory + module-level `app`
    deps.py                 # request-scoped DB session
    schemas.py              # PoiOut / PoiDetailOut / PlaceOut / ScoreOut
    attributions.py         # source -> attribution string
    routers/pois.py         # /pois/nearby, /pois/{id}
    routers/places.py       # /places, /places/{id}, /places/{id}/highlights
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
| **Wikivoyage** | CC BY-SA | MediaWiki API (per page) | `place` layer (destination prose + practical info), POI listings, "Do" activity flag | active |
| **Atlas Obscura** | proprietary | N/A | offbeat inspiration | **excluded** (ToS bars scraping; use a curated name seed only) |

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
        uuid place_id FK
        text[] categories "unified taxonomy"
        text short_description
        jsonb descriptions "lang -> text"
        jsonb images
        jsonb source_xids
        jsonb field_provenance "field -> winning source"
        int pageviews_30d
        int sitelink_count
        text wikipedia_title
        bool is_destination
    }
    SOURCE_RECORD {
        uuid id PK
        uuid poi_id FK
        uuid place_id FK
        text source "osm|opentripmap|wikidata|wikivoyage"
        text source_id
        text lang
        jsonb payload "verbatim"
        text license
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
        jsonb names
        geography geom "centroid"
        jsonb descriptions
        jsonb practical_info "get_in / get_around / stay_safe ..."
        text wikivoyage_title
    }
```

Two deliberate choices:

- **`field_provenance`** records which source won each conflated field, so any value
  traces back (e.g. `{"geom":"osm","short_description":"opentripmap"}`).
- **`poi_score.components`** stores raw signal values, so a learning-to-rank model can
  later train on the exact features the heuristic used without requiring a schema change.

`PLACE` is populated by the Wikivoyage layer (city/district prose + practical info).
POIs created from Wikivoyage listings inherit that `place_id`; `/places/{id}/highlights`
additionally scopes spatially around the place centroid so it surfaces the whole nearby
POI set, not just the listings.

Migrations: `0001_initial` (schema + PostGIS), `0002_enrichment` (`pageviews_30d`,
`sitelink_count`, `wikipedia_title`, `enriched_at`), `0003_destination_flag`
(`is_destination`).

---

## 4. Pipeline

Two ingestion entry points:

- **POI ingest** (geo): `ingest --source osm|opentripmap --lat --lon --radius-m`
- **Place ingest** (page): `ingest-place --title "City/District"` (Wikivoyage)

Both land into `source_record`; then the canonical order is **resolve → enrich**. The
`pipeline` command runs `resolve` then `enrich`, which keeps scores and flags consistent
after any ingest.

```mermaid
sequenceDiagram
    participant CLI
    participant SRC as Source
    participant DB as Postgres
    participant WD as Wikidata/Pageviews

    CLI->>SRC: ingest (OSM/OTM) or ingest-place (Wikivoyage)
    SRC->>DB: land_raw(RawDoc)   [content-hash skip if unchanged]
    Note over DB: ingest-place also upserts a 'place' row

    CLI->>DB: resolve()
    loop each unresolved source_record
        DB->>DB: record_to_drafts()
        alt QID match
            DB->>DB: link to existing POI
        else spatial + name match (distance under 80m, similarity 0.85+)
            DB->>DB: link to nearby POI
        else
            DB->>DB: create new POI
        end
        DB->>DB: propagate place_id and reconflate_and_score()
    end

    CLI->>DB: enrich()  [POIs with QID, not yet enriched]
    DB->>WD: SPARQL batch (labels, sitelinks, P18, P31, enwiki) + pageviews
    WD-->>DB: info
    DB->>DB: land wikidata source_record + link + reconflate_and_score()
```

Operational properties:

- **Idempotent ingest**: `land_raw` keys on `(source, source_id, lang)` and skips
  unchanged payloads via `content_hash`.
- **Rebuild-safe enrichment**: Wikidata metrics (`sitelinks`, `pageviews_30d`,
  `instance_of`, `enwiki_title`) live inside the Wikidata `source_record` payload, so
  `resolve --rebuild` restores everything with **no network calls**. You only pay the
  Wikidata/pageviews cost on first enrich (or an explicit `enrich --refresh`).
- **Crash-safe ingest**: `run_ingest` commits every 100 records.

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
    M --> R[propagate place_id\nreconflate_and_score]
    N --> R
    E --> R
```

- **QID exact match** is the golden path: OSM tags, OTM, and many Wikivoyage listings
  carry `wikidata` ids, so the same real place across sources collapses for free.
- **Spatial + name** blocks candidates with `ST_DWithin` (≤ 80 m) and scores names with
  `rapidfuzz.token_sort_ratio` on accent-stripped strings (threshold 0.85). Both tunable.

**Conflation** chooses each field by per-field source priority (recorded in
`field_provenance`):

| Field | Priority (highest → lowest) | Rationale |
|---|---|---|
| `geom` | osm → wikidata → opentripmap | most authoritative coordinates |
| name / `names` | wikidata → osm → wikivoyage → opentripmap | clean multilingual labels |
| description | **wikivoyage** → opentripmap → osm → wikidata | richest human-written prose wins |
| `categories`, `raw_kinds`, `images`, `source_xids` | union / merge | N/A |
| `importance_raw` (rate) | OpenTripMap only | only OTM provides it |

Wikivoyage listing kinds map into the taxonomy (`see`/`do`→`other`, `eat`→`food`,
`drink`→`nightlife`, `buy`→`market`; `sleep` is skipped). `canonical_name` is taken from
merged `names` in the default language when present.

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
        WVD[in wikivoyage Do]
        OSP[osm leisure/sport]
        DEST[is_destination]
    end

    D & I & S & L & P --> CR[content_richness]
    PV & SL & R --> POP[popularity]
    CAT & WVD & OSP --> ACT[activity_score]
    CR & POP & DEST --> GEM[hidden_gem_score]
```

**content_richness** (documentation depth). `has_practical_info` is populated from OSM
(`opening_hours`/`website`/`phone`/`fee`), OTM (`address`/`url`), and Wikivoyage
(`hours`/`price`/`address`/`phone`); description length uses the **full** description:

```
0.20 · has_description
+ 0.20 · min(description_len / 1500, 1)
+ 0.15 · min(image_count / 3, 1)
+ 0.20 · min(source_count / 4, 1)
+ 0.15 · has_practical_info
+ 0.10 · min(lang_count / 3, 1)
```

**popularity**: weighted mean over the *evidence* present; OSM presence is a weak prior:

```
pageviews:  min(log10(views + 1) / 5, 1)   weight 0.55
sitelinks:  min(sitelinks / 40, 1)         weight 0.30
otm_rate:   (rate - 1) / 6                  weight 0.15
+ 0.05 nudge if present in OSM; fallback 0.10 if only OSM, else 0.0
```

**activity_score**: per-category prior, boosted by Wikivoyage "Do" membership and OSM
leisure/sport tags (both now wired live):

```
clamp( activity_prior(categories) + 0.30·in_wikivoyage_do + 0.20·osm_leisure_sport )
```

Priors (excerpt): `hiking 0.95, water_activity 0.90, sport 0.90, amusement 0.85,
market 0.70, viewpoint 0.60, park 0.60, food 0.55, art 0.45, museum 0.40,
historic 0.30, monument 0.25, water_body 0.25, public_art 0.10, other 0.20`.

**hidden_gem_score**: interesting but not famous, gated against junk and non-places:

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
    B -->|no| C{Wikidata P31 in\nNON_DESTINATION_INSTANCES?}
    C -->|yes| X
    C -->|no| F{has any real category?}
    F -->|yes| Y[destination]
    F -->|no| X
```

Gated only on `hidden_gem_score` and the API's destination filters; `content_richness`
and `popularity` remain raw component signals.

---

## 7. HTTP API

FastAPI over PostGIS. Run with `traveldata serve`; interactive docs at `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /pois/nearby` | spatial discovery (`ST_DWithin`) ordered by a score |
| `GET /pois/{id}` | full POI detail with descriptions + attributions |
| `GET /places` | list ingested destinations |
| `GET /places/{id}` | destination prose + practical info |
| `GET /places/{id}/highlights` | top destinations near a place, by score |

`/pois/nearby` params: `lat`, `lon`, `radius_m`, `categories` (comma-separated),
`min_hidden_gem`, `sort` (`hidden_gem_score`|`activity_score`|`popularity`|`content_richness`|`distance`),
`destinations_only` (default `true`), `limit`.
`/places/{id}/highlights` params: `sort`, `radius_m` (around the place centroid), `limit`
(always destination-filtered).

Every result carries its scores, `field_provenance`, and `attributions` assembled from
the real contributing sources, making it license-compliant by construction.

---

## 8. CLI

```
traveldata sources                 # list connectors + licenses
traveldata ingest --source osm|opentripmap --lat .. --lon .. --radius-m ..
traveldata ingest-place --title "City/District" [--lang en] [--level district]
traveldata stats                   # source_record counts by source
traveldata resolve [--rebuild]
traveldata enrich [--refresh] [--no-pageviews]
traveldata pipeline [--rebuild]    # resolve then enrich (run after any ingest)
traveldata top --metric <m> [--limit N]
traveldata serve [--host --port --reload]
```

---

## 9. Configuration

Overridable via `TRAVELDATA_<UPPER>` env vars or a `.env` file.

| Variable | Default / note |
|---|---|
| `TRAVELDATA_DATABASE_URL` | `postgresql+psycopg://...` (PostGIS required) |
| `TRAVELDATA_OPENTRIPMAP_API_KEY` | required for OTM ingest |
| `TRAVELDATA_OVERPASS_URL` | `https://overpass-api.de/api/interpreter` |
| `TRAVELDATA_WIKIDATA_SPARQL_URL` | `https://query.wikidata.org/sparql` |
| `TRAVELDATA_DEFAULT_LANG` | `en` |
| `TRAVELDATA_HTTP_MIN_INTERVAL_S` | per-connector politeness throttle |
| `TRAVELDATA_USER_AGENT` | set a real contact string (WDQS/Wikimedia require it) |

(Wikivoyage uses the `lang` argument to pick the `{lang}.wikivoyage.org` edition.)

---

## 10. Running locally

```bash
docker run -d --name traveldata \
  -e POSTGRES_PASSWORD=traveldata -e POSTGRES_DB=traveldata \
  -p 5433:5432 postgis/postgis:16-3.4

cat >> .env <<'ENV'
TRAVELDATA_DATABASE_URL=postgresql+psycopg://postgres:traveldata@localhost:5433/traveldata
TRAVELDATA_OPENTRIPMAP_API_KEY=your_key_here
TRAVELDATA_USER_AGENT=traveldata/0.1 (you@example.com)
ENV

uv sync                                  # installs core + extras you've added
uv pip install -e ".[dev,serve,wikivoyage]"
uv run alembic upgrade head

uv run traveldata ingest --source osm         --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata ingest --source opentripmap --lat 48.8606 --lon 2.3376 --radius-m 1500
uv run traveldata ingest-place --title "Paris/1st arrondissement" --level district
uv run traveldata pipeline               # resolve + enrich

uv run traveldata serve --reload         # http://127.0.0.1:8000/docs
```

---

## 11. Licensing & compliance

- **Wikidata**: CC0 (no attribution required); the join layer.
- **OSM**: ODbL: attribution ("© OpenStreetMap contributors") + share-alike.
- **OpenTripMap**: aggregates OSM/Wikidata/Wikipedia; inherit those, carry attribution
  downstream, respect API ToS and rate limits.
- **Wikipedia extracts / Wikivoyage**: CC BY-SA: attribution + share-alike.
- **Atlas Obscura**: proprietary; **not** scraped or stored. Only a hand-curated list of
  place *names* (facts) may be used, then re-resolved through the open sources.

Every record keeps `license` + `source_url`; the API exposes `attributions`.

---

## 12. Known limitations & tuning knobs

- **Wikivoyage coverage** is per-ingested-page: district pages (e.g.
  `Paris/1st arrondissement`) carry the listings; the top-level city page is mostly a
  districts index. Listings without `lat`/`long` are skipped (our model requires
  coordinates, as geocoding-by-name is a later refinement). `level` is passed manually.
- **`/places/{id}/highlights`** is geo-scoped around the place centroid (a `radius_m`
  param), not strictly by `place_id` membership. This is robust, but tune the radius per place.
- **Non-destination filtering** is a hand-curated `P31` blocklist plus the `public_art`
  rule. The principled fix is a one-time Wikidata `P279` (subclass-of) walk to "work of
  art" (Q838948), cached per QID.
- **`public_art` is a hard exclusion** (drops famous public art too); relax by keeping it
  when `sitelink_count` is high.
- **`content_richness` / `popularity` are not gated** by `is_destination` (raw component
  signals by design).
- **Discovery is single-bbox** per ingest (no tiling) and **resolution is per-record**
  (not batch-optimized), which works fine at city scale.

---

## 13. Roadmap

1. **P279 instance classification**: replace the hand-curated artwork blocklist.
2. **Recommender**: sentence-transformer description embeddings into `pgvector` for
   "more like this"; train LTR on `poi_score.components` once engagement data exists.
3. **Scale**: tile `ingest` over a bbox; optionally switch Wikivoyage to dump-parsing to
   ingest whole cities/countries instead of one page/radius at a time.
4. **Geocode coordinate-less listings**: recover the Wikivoyage listings currently
   skipped for missing `lat`/`long`.
5. **Agentic layer**: the deferred piece; this dataset + API is a clean tool surface.
