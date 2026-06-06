"""Connector contract and the data objects that flow between pipeline stages.

The key design rule: I/O lives in `Connector.fetch` (impure, network), while turning
a raw payload into canonical drafts lives in `normalize.mappers` (pure, unit-tested).
That split is what makes the hard logic testable without hitting any live API.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional


def content_hash(payload: dict) -> str:
    """Stable hash of a payload for change detection / idempotent reruns."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkUnit:
    """A unit of fetch work, usually one place/bbox to scan for POIs."""

    lat: float
    lon: float
    place_id: Optional[str] = None
    radius_m: Optional[int] = None
    bbox: Optional[tuple[float, float, float, float]] = None  # (s, w, n, e)
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RawDoc:
    """A verbatim source payload, ready to be landed into `source_record`."""

    source: str
    source_id: str
    payload: dict
    license: str
    lang: Optional[str] = None
    source_url: Optional[str] = None

    @property
    def hash(self) -> str:
        return content_hash(self.payload)


@dataclass
class CanonicalPoiDraft:
    """Source-agnostic POI, pre-resolution. Multiple drafts may resolve to one POI."""

    source: str
    source_id: str
    canonical_name: str
    lat: float
    lon: float
    names: dict[str, str] = field(default_factory=dict)
    wikidata_qid: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    raw_kinds: list[str] = field(default_factory=list)
    short_description: Optional[str] = None
    descriptions: dict[str, str] = field(default_factory=dict)
    images: list[dict] = field(default_factory=list)
    source_xids: dict[str, str] = field(default_factory=dict)
    importance_raw: Optional[float] = None
    heritage: bool = False
    license: str = ""
    source_url: Optional[str] = None


class Connector(ABC):
    """Every source implements this. `discover`/`fetch` do I/O; mapping is pure."""

    source: str
    license: str

    @abstractmethod
    def discover(self, lat: float, lon: float, **kw) -> Iterable[WorkUnit]:
        """Turn a place reference into one or more fetch work units."""

    @abstractmethod
    def fetch(self, unit: WorkUnit) -> Iterator[RawDoc]:
        """Yield raw source documents for a work unit. Network lives here."""

    @abstractmethod
    def to_drafts(self, raw: RawDoc) -> list[CanonicalPoiDraft]:
        """Pure mapping from a raw doc to canonical drafts (delegates to normalize)."""
