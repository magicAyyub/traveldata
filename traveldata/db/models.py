"""ORM models mirroring the normalized schema (PostGIS-targeted).

Geometry columns use GeoAlchemy2; DDL requires Postgres + PostGIS. Importing this
module is driver-free, but creating tables needs a real PostGIS database.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import ARRAY, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Place(Base):
    __tablename__ = "place"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wikidata_qid: Mapped[str | None] = mapped_column(Text, unique=True)
    level: Mapped[str] = mapped_column(String(16))  # country|region|city|district
    canonical_name: Mapped[str] = mapped_column(Text)
    names: Mapped[dict] = mapped_column(JSONB, default=dict)
    geom: Mapped[object | None] = mapped_column(Geography("POINT", srid=4326))
    parent_place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("place.id"))
    wikivoyage_title: Mapped[str | None] = mapped_column(Text)
    descriptions: Mapped[dict] = mapped_column(JSONB, default=dict)
    practical_info: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())


class Poi(Base):
    __tablename__ = "poi"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    wikidata_qid: Mapped[str | None] = mapped_column(Text, index=True)
    canonical_name: Mapped[str] = mapped_column(Text)
    names: Mapped[dict] = mapped_column(JSONB, default=dict)
    geom: Mapped[object] = mapped_column(Geography("POINT", srid=4326))
    geohash: Mapped[str | None] = mapped_column(String(12), index=True)
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("place.id"))
    country_code: Mapped[str | None] = mapped_column(String(2))
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    raw_kinds: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    short_description: Mapped[str | None] = mapped_column(Text)
    descriptions: Mapped[dict] = mapped_column(JSONB, default=dict)
    images: Mapped[list] = mapped_column(JSONB, default=list)
    source_xids: Mapped[dict] = mapped_column(JSONB, default=dict)
    field_provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    pageviews_30d: Mapped[int | None] = mapped_column()
    sitelink_count: Mapped[int | None] = mapped_column()
    wikipedia_title: Mapped[str | None] = mapped_column(Text)
    is_destination: Mapped[bool] = mapped_column(default=True)
    enriched_at: Mapped[datetime | None] = mapped_column()
    first_seen_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    scores: Mapped[list["PoiScore"]] = relationship(back_populates="poi")


class SourceRecord(Base):
    __tablename__ = "source_record"
    __table_args__ = (UniqueConstraint("source", "source_id", "lang"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    poi_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("poi.id"))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("place.id"))
    source: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(8))
    payload: Mapped[dict] = mapped_column(JSONB)
    license: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(default=func.now())


class PoiLink(Base):
    __tablename__ = "poi_link"

    poi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("poi.id"), primary_key=True)
    source_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_record.id"), primary_key=True
    )
    match_method: Mapped[str | None] = mapped_column(String(32))  # wikidata_qid|spatial_name|manual
    match_score: Mapped[float | None] = mapped_column()


class PoiScore(Base):
    __tablename__ = "poi_score"

    poi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("poi.id"), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    popularity: Mapped[float | None] = mapped_column()
    content_richness: Mapped[float | None] = mapped_column()
    activity_score: Mapped[float | None] = mapped_column()
    hidden_gem_score: Mapped[float | None] = mapped_column()
    components: Mapped[dict] = mapped_column(JSONB, default=dict)
    scored_at: Mapped[datetime] = mapped_column(default=func.now())

    poi: Mapped[Poi] = relationship(back_populates="scores")
