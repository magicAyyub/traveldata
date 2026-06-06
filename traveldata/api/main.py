"""Minimal FastAPI serving surface. Endpoints are wired to the schema; the DB-backed
queries (PostGIS ST_DWithin etc.) land with the persistence slice. FastAPI/uvicorn are
optional extras so the core package stays import-light.
"""
from __future__ import annotations

try:
    from fastapi import FastAPI
except ImportError:  # FastAPI is an optional serving dependency
    FastAPI = None  # type: ignore

from pydantic import BaseModel


class PoiOut(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = {}
    lat: float
    lon: float
    categories: list[str] = []
    short_description: str | None = None
    hidden_gem_score: float | None = None
    activity_score: float | None = None
    source_xids: dict[str, str] = {}
    attributions: list[str] = []  # provenance surfaced to clients


def create_app():
    if FastAPI is None:
        raise RuntimeError("Install fastapi+uvicorn to run the API (pip install fastapi uvicorn)")
    app = FastAPI(title="traveldata", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # Planned (persistence slice):
    #   GET /pois/nearby?lat=&lon=&radius_m=&categories=&min_hidden_gem=  (ST_DWithin)
    #   GET /pois/{id}
    #   GET /places/{id}/highlights?kind=activity|hidden_gem
    #   GET /pois/search?q=&lang=
    return app
