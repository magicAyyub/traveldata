"""Connector registry. Add new sources here as they land."""
from .base import CanonicalPoiDraft, Connector, RawDoc, WorkUnit
from .opentripmap import OpenTripMapConnector
from .osm_overpass import OverpassConnector

CONNECTORS = {
    "opentripmap": OpenTripMapConnector,
    "osm": OverpassConnector,
}

__all__ = [
    "Connector", "RawDoc", "WorkUnit", "CanonicalPoiDraft",
    "OpenTripMapConnector", "OverpassConnector", "CONNECTORS",
]
