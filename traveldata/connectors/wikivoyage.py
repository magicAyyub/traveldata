"""Wikivoyage page fetch via the MediaWiki Action API (per-page; dumps are the scale path)."""
from __future__ import annotations

from ..cache.http_cache import RateLimitedClient


def fetch_wikitext(title: str, lang: str = "en", client: RateLimitedClient | None = None) -> str:
    client = client or RateLimitedClient()
    url = f"https://{lang}.wikivoyage.org/w/api.php"
    data = client.get_json(url, {
        "action": "parse", "page": title, "prop": "wikitext",
        "format": "json", "redirects": 1,
    })
    if "error" in data:
        raise ValueError(f"wikivoyage: {data['error'].get('info')}")
    return data["parse"]["wikitext"]["*"]