"""Batched Wikidata SPARQL: labels/descriptions, sitelinks, image, enwiki title, P31."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..cache.http_cache import RateLimitedClient
from ..config import settings

_GROUP_SEP = "‖"
_FIELD_SEP = "|"


@dataclass
class WikidataInfo:
    qid: str
    labels: dict[str, str] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)
    sitelink_count: int | None = None
    image: str | None = None
    enwiki_title: str | None = None
    instance_of: list[str] = field(default_factory=list)


def _build_query(qids: list[str], langs: tuple[str, ...]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    langs_in = ", ".join(f'"{l}"' for l in langs)
    return f"""
SELECT ?item ?sitelinks ?image ?title
  (GROUP_CONCAT(DISTINCT CONCAT(?llang,"{_FIELD_SEP}",?label); separator="{_GROUP_SEP}") AS ?labels)
  (GROUP_CONCAT(DISTINCT CONCAT(?dlang,"{_FIELD_SEP}",?desc); separator="{_GROUP_SEP}") AS ?descs)
  (GROUP_CONCAT(DISTINCT STRAFTER(STR(?instance),"entity/"); separator="|") AS ?instances)
WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wikibase:sitelinks ?sitelinks. }}
  OPTIONAL {{ ?item wdt:P18 ?image. }}
  OPTIONAL {{ ?item wdt:P31 ?instance. }}
  OPTIONAL {{ ?item rdfs:label ?label. BIND(LANG(?label) AS ?llang) FILTER(?llang IN ({langs_in})) }}
  OPTIONAL {{ ?item schema:description ?desc. BIND(LANG(?desc) AS ?dlang) FILTER(?dlang IN ({langs_in})) }}
  OPTIONAL {{ ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?title. }}
}}
GROUP BY ?item ?sitelinks ?image ?title
"""


def _v(b: dict, k: str) -> str | None:
    return b[k]["value"] if k in b and b[k].get("value") not in (None, "") else None


def _decode_pairs(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if raw:
        for pair in raw.split(_GROUP_SEP):
            if _FIELD_SEP in pair:
                lg, txt = pair.split(_FIELD_SEP, 1)
                out.setdefault(lg, txt)
    return out


def parse_binding(b: dict) -> WikidataInfo:
    sl = _v(b, "sitelinks")
    instances = _v(b, "instances")
    return WikidataInfo(
        qid=b["item"]["value"].rsplit("/", 1)[-1],
        labels=_decode_pairs(_v(b, "labels")),
        descriptions=_decode_pairs(_v(b, "descs")),
        sitelink_count=int(sl) if sl else None,
        image=_v(b, "image"),
        enwiki_title=_v(b, "title"),
        instance_of=instances.split("|") if instances else [],
    )


def fetch_wikidata(qids: list[str], langs: tuple[str, ...] = ("en", "fr", "es", "de", "it"),
                   client: RateLimitedClient | None = None, chunk: int = 50) -> dict[str, WikidataInfo]:
    client = client or RateLimitedClient()
    out: dict[str, WikidataInfo] = {}
    for i in range(0, len(qids), chunk):
        data = client.get_json(settings.wikidata_sparql_url,
                               {"query": _build_query(qids[i:i + chunk], langs), "format": "json"})
        for b in data.get("results", {}).get("bindings", []):
            info = parse_binding(b)
            out[info.qid] = info
    return out