"""Central configuration. Override any field with TRAVELDATA_<UPPER> env vars or .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAVELDATA_", env_file=".env", extra="ignore"
    )

    # Storage
    database_url: str = (
        "postgresql+psycopg://traveldata:traveldata@localhost:5432/traveldata"
    )

    # OpenTripMap (primary POI connector). Free key registration is historically
    # flaky -- keep Overpass as a drop-in fallback (see connectors/osm_overpass.py).
    opentripmap_api_key: str = ""
    opentripmap_base_url: str = "https://api.opentripmap.com/0.1"

    # OSM / Overpass (fallback POI source + tag richness)
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Wikidata (golden join key + multilingual, CC0)
    wikidata_sparql_url: str = "https://query.wikidata.org/sparql"

    # Behaviour
    default_lang: str = "en"
    http_min_interval_s: float = 1.0  # politeness throttle per connector
    http_timeout_s: float = 30.0
    user_agent: str = "traveldata/0.1 (+https://example.com; data@example.com)"


settings = Settings()
