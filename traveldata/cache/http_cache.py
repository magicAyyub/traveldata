"""HTTP plumbing shared by connectors: a throttle + retry wrapper around httpx.

A persistent on-disk cache (hishel) is the intended next step; for now this keeps
requests polite and resilient. The client is injectable so tests pass a MockTransport.
"""
from __future__ import annotations

import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=settings.http_timeout_s,
        headers={"User-Agent": settings.user_agent},
        transport=transport,
    )


class RateLimitedClient:
    """Wraps an httpx.Client with a minimum inter-request interval + retry."""

    def __init__(self, client: httpx.Client | None = None, min_interval_s: float | None = None):
        self._client = client or make_client()
        self._min_interval = (
            min_interval_s if min_interval_s is not None else settings.http_min_interval_s
        )
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def get_json(self, url: str, params: dict | None = None) -> dict | list:
        self._throttle()
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def post_text(self, url: str, data: dict | None = None) -> dict | list:
        self._throttle()
        resp = self._client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()
