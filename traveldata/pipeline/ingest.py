"""Ingestion runner: fetch -> land raw source_records. One commit per run, idempotent."""
from __future__ import annotations

from ..connectors.base import Connector
from ..db.base import get_sessionmaker
from ..raw.store import land_raw


def run_ingest(connector: Connector, lat: float, lon: float,
               radius_m: int = 3000, limit: int | None = None) -> dict[str, int]:
    Session = get_sessionmaker()
    counts = {"new": 0, "updated": 0, "unchanged": 0, "total": 0}
    with Session() as session:
        try:
            stop = False
            for unit in connector.discover(lat, lon, radius_m=radius_m):
                if stop:
                    break
                for raw in connector.fetch(unit):
                    _, status = land_raw(session, raw)
                    counts[status] += 1
                    counts["total"] += 1
                    if limit and counts["total"] >= limit:
                        stop = True
                        break
            session.commit()
        except Exception:
            session.rollback()
            raise
    return counts