"""FastAPI app. Run: `traveldata serve` or `uvicorn traveldata.api.main:app`."""
from __future__ import annotations

try:
    from fastapi import FastAPI
except ImportError:
    FastAPI = None  # type: ignore


def create_app():
    if FastAPI is None:
        raise RuntimeError("Install serving deps: uv pip install -e '.[serve]'")
    from .routers import places, pois

    app = FastAPI(title="traveldata", version="0.1.0")
    app.include_router(pois.router)
    app.include_router(places.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app() if FastAPI is not None else None