"""Marketplace catalog helpers for external recommendation data."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_FILE = PROJECT_ROOT / "data" / "catalog.json"


def _ensure_catalog_exists() -> None:
    if not CATALOG_FILE.exists():
        raise FileNotFoundError(
            "Catalog file not found. Please provide data/catalog.json with curated items."
        )


@lru_cache(maxsize=1)
def load_catalog() -> List[dict]:
    _ensure_catalog_exists()
    with CATALOG_FILE.open("r", encoding="utf-8") as fp:
        catalog = json.load(fp)
    for item in catalog:
        tags = item.get("style_tags", [])
        if isinstance(tags, str):
            item["style_tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
    return catalog


def catalog_by_category() -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = {}
    for item in load_catalog():
        category = item.get("category", "기타")
        buckets.setdefault(category, []).append(item)
    return buckets


def filter_catalog(
    *,
    categories: Iterable[str] | None = None,
    style_preferences: Iterable[str] | None = None,
    seasons: Iterable[str] | None = None,
) -> List[dict]:
    """Return catalog items filtered by category, style tags, and season."""

    categories = list(categories or [])
    style_preferences = [s for s in (style_preferences or []) if s]
    seasons = [s for s in (seasons or []) if s]

    def _season_match(item_seasons: List[str]) -> bool:
        if not seasons:
            return True
        item_tags = {season for season in item_seasons}
        return bool(item_tags.intersection(seasons) or "사계절" in item_tags)

    def _style_match(item_tags: List[str]) -> bool:
        if not style_preferences:
            return True
        return bool(set(item_tags).intersection(style_preferences))

    filtered: List[dict] = []
    for item in load_catalog():
        if categories and item.get("category") not in categories:
            continue
        if not _season_match(item.get("season", [])):
            continue
        if not _style_match(item.get("style_tags", [])):
            continue
        filtered.append(item)
    return filtered


