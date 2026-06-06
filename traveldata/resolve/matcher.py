"""Name normalization + similarity for the spatial+name match path."""
from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str, b: str) -> float:
    """0..1; token-sort handles word-order differences (e.g. 'Tour Eiffel')."""
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(normalize_name(a), normalize_name(b)) / 100.0