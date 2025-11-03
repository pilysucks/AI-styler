"""Marketplace catalog helpers for external recommendation data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import sources


logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_FILE = PROJECT_ROOT / "data" / "catalog.json"


def _load_static_catalog() -> List[dict]:
    if not CATALOG_FILE.exists():
        return []
    with CATALOG_FILE.open("r", encoding="utf-8") as fp:
        catalog = json.load(fp)
    for item in catalog:
        tags = item.get("style_tags", [])
        if isinstance(tags, str):
            item["style_tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
        item.setdefault("source", "static")
    return catalog


def _deduplicate(items: Iterable[dict]) -> List[dict]:
    seen: set[str] = set()
    results: List[dict] = []
    for item in items:
        key = item.get("product_url") or item.get("source_id") or item.get("name")
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def load_catalog(
    *,
    include_static: bool = True,
    include_musinsa: bool = True,
    include_kream: bool = True,
    musinsa_limit: int = 150,
    kream_limit: int = 150,
    musinsa_cookie: Optional[str] = None,
    kream_cookie: Optional[str] = None,
    include_meta: bool = False,
) -> List[dict] | Tuple[List[dict], List[str]]:
    """Load catalog entries from static data and external providers."""

    aggregated: List[dict] = []
    errors: List[str] = []

    if include_static:
        try:
            aggregated.extend(_load_static_catalog())
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Failed to load static catalog: %s", exc)
            errors.append(f"정적 카탈로그 로드 실패: {exc}")

    if include_musinsa and musinsa_limit > 0:
        try:
            aggregated.extend(
                sources.fetch_musinsa_catalog(limit=musinsa_limit, cookie_header=musinsa_cookie)
            )
        except Exception as exc:  # pragma: no cover - network failures handled gracefully
            logger.warning("Musinsa catalog fetch failed: %s", exc, exc_info=True)
            errors.append(f"무신사 데이터 수집 실패: {exc}")

    if include_kream and kream_limit > 0:
        try:
            aggregated.extend(
                sources.fetch_kream_catalog(limit=kream_limit, cookie_header=kream_cookie)
            )
        except Exception as exc:  # pragma: no cover - network failures handled gracefully
            logger.warning("KREAM catalog fetch failed: %s", exc, exc_info=True)
            errors.append(f"크림 데이터 수집 실패: {exc}")

    deduplicated = _deduplicate(aggregated)
    if include_meta:
        return deduplicated, errors
    return deduplicated


def catalog_by_category(**kwargs) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = {}
    catalog = load_catalog(**kwargs)
    if isinstance(catalog, tuple):
        catalog = catalog[0]
    for item in catalog:
        category = item.get("category", "기타")
        buckets.setdefault(category, []).append(item)
    return buckets


def filter_catalog(
    *,
    categories: Iterable[str] | None = None,
    style_preferences: Iterable[str] | None = None,
    seasons: Iterable[str] | None = None,
    **load_kwargs,
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

    catalog = load_catalog(**load_kwargs)
    if isinstance(catalog, tuple):
        catalog = catalog[0]

    filtered: List[dict] = []
    for item in catalog:
        if categories and item.get("category") not in categories:
            continue
        if not _season_match(item.get("season", [])):
            continue
        if not _style_match(item.get("style_tags", [])):
            continue
        filtered.append(item)
    return filtered


