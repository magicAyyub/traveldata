"""Declarative base + lazy engine factory.

Engine creation is deferred (not module-level) so importing models never requires a
DB driver or a running Postgres. Call get_engine()/get_session() at runtime.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    pass


def get_engine(url: str | None = None):
    return create_engine(url or settings.database_url, future=True)


def get_sessionmaker(engine=None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), autoflush=False, future=True)
