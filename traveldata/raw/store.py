"""Land raw payloads into source_record. Idempotent: unchanged content is skipped."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import RawDoc
from ..db.models import SourceRecord


def land_raw(session: Session, raw: RawDoc) -> tuple[SourceRecord, str]:
    """Upsert a RawDoc. Returns (record, status) where status is new|updated|unchanged."""
    existing = session.scalar(
        select(SourceRecord).where(
            SourceRecord.source == raw.source,
            SourceRecord.source_id == raw.source_id,
            SourceRecord.lang == raw.lang,
        )
    )
    h = raw.hash
    if existing is not None:
        if existing.content_hash == h:
            return existing, "unchanged"
        existing.payload = raw.payload
        existing.content_hash = h
        existing.source_url = raw.source_url
        existing.license = raw.license
        return existing, "updated"

    rec = SourceRecord(
        source=raw.source, source_id=raw.source_id, lang=raw.lang,
        payload=raw.payload, license=raw.license,
        source_url=raw.source_url, content_hash=h,
    )
    session.add(rec)
    return rec, "new"