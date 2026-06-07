"""Request-scoped DB session dependency."""
from __future__ import annotations

from ..db.base import get_sessionmaker

SessionLocal = get_sessionmaker()


def get_session():
    with SessionLocal() as session:
        yield session