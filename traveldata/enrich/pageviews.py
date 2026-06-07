"""Wikimedia pageviews REST API -> 30-day total (a strong, free popularity proxy)."""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from ..cache.http_cache import RateLimitedClient

_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def monthly_views(title: str, project: str = "en.wikipedia",
                  client: RateLimitedClient | None = None) -> int:
    client = client or RateLimitedClient()
    end = date.today()
    start = end - timedelta(days=30)
    safe = quote(title.replace(" ", "_"), safe="")
    url = (f"{_BASE}/{project}/all-access/all-agents/{safe}/daily/"
           f"{start:%Y%m%d}/{end:%Y%m%d}")
    try:
        data = client.get_json(url)
    except Exception:
        return 0
    return sum(item.get("views", 0) for item in data.get("items", []))