"""Recommendation logic for the AI Styler app."""

from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import marketplace


COLOR_FAMILIES: Dict[str, List[str]] = {
    "모노": ["블랙", "화이트", "아이보리", "그레이", "차콜"],
    "뉴트럴": ["베이지", "브라운", "카멜", "크림"],
    "딥": ["네이비", "딥그린", "버건디"],
    "브라이트": ["레드", "옐로우", "오렌지", "블루", "핑크"],
    "파스텔": ["민트", "라벤더", "라일락", "소라"],
}

MANDATORY_CATEGORIES = ["신발"]
OPTIONAL_CATEGORIES = ["아우터", "모자"]


def _normalise_tags(raw: Optional[Iterable[str]]) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        tokens = [token.strip() for token in raw.split(",")]
    else:
        tokens = [str(token).strip() for token in raw]
    return [token for token in tokens if token]


def _color_family(color: str) -> str:
    color = (color or "").replace(" ", "").strip()
    if not color:
        return "기타"
    for family, palette in COLOR_FAMILIES.items():
        if any(color.startswith(palette_color) for palette_color in palette):
            return family
    return "기타"


def _style_alignment(item_tags: Iterable[str], preferences: Iterable[str]) -> float:
    item_set = set(_normalise_tags(item_tags))
    pref_set = set(_normalise_tags(preferences))
    if not pref_set:
        return 0.6 if item_set else 0.4
    intersection = item_set.intersection(pref_set)
    return len(intersection) / len(pref_set)


def _season_alignment(item_seasons: Iterable[str], target_seasons: Iterable[str]) -> float:
    seasons = set(_normalise_tags(item_seasons))
    if "사계절" in seasons:
        seasons.add("봄")
        seasons.add("여름")
        seasons.add("가을")
        seasons.add("겨울")
    target = set(_normalise_tags(target_seasons))
    if not target:
        return 0.5
    if seasons.intersection(target):
        return 1.0
    return 0.2


def _color_alignment(items: List[pd.Series]) -> float:
    families = [_color_family(item.get("color", "")) for item in items]
    family_counts = {family: families.count(family) for family in set(families)}
    dominant_count = max(family_counts.values()) if family_counts else 0
    return dominant_count / max(len(families), 1)


def _score_outfit(items: List[pd.Series], profile: dict) -> float:
    style_scores = [_style_alignment(item.get("style_tags", []), profile.get("style_preferences", [])) for item in items]
    season_scores = [_season_alignment(item.get("season", []), profile.get("season", [])) for item in items]

    score = 0.5 * float(np.mean(style_scores) if style_scores else 0)
    score += 0.3 * _color_alignment(items)
    score += 0.2 * float(np.mean(season_scores) if season_scores else 0)
    return round(score, 3)


def _inventory_by_category(df: pd.DataFrame, category: str) -> List[pd.Series]:
    matches = df[df["category"] == category]
    return [row for _, row in matches.iterrows()]


def outfit_suggestions(
    inventory_df: pd.DataFrame,
    profile: dict,
    max_results: int = 6,
) -> List[dict]:
    """Return outfits built from the user's inventory."""

    if inventory_df.empty:
        return []

    if inventory_df[inventory_df["category"] == "신발"].empty:
        return []

    tops = _inventory_by_category(inventory_df, "상의")
    onepieces = _inventory_by_category(inventory_df, "원피스")
    skirts = _inventory_by_category(inventory_df, "스커트")
    bottoms = _inventory_by_category(inventory_df, "바지") + skirts
    shoes = _inventory_by_category(inventory_df, "신발")
    outers = _inventory_by_category(inventory_df, "아우터")
    caps = _inventory_by_category(inventory_df, "모자")

    combos: List[dict] = []
    if tops and bottoms:
        for top, bottom, shoe in itertools.product(tops, bottoms, shoes):
            base_items = [top, bottom, shoe]
            candidate_items = base_items.copy()

            if outers:
                outer = max(
                    outers,
                    key=lambda item: _style_alignment(item.get("style_tags", []), profile.get("style_preferences", [])),
                )
                candidate_items.append(outer)

            if caps:
                cap = max(
                    caps,
                    key=lambda item: _season_alignment(item.get("season", []), profile.get("season", [])),
                )
                candidate_items.append(cap)

            score = _score_outfit(candidate_items, profile)
            combos.append(
                {
                    "items": candidate_items,
                    "score": score,
                    "style_tags": sorted(
                        set(
                            itertools.chain.from_iterable(
                                _normalise_tags(item.get("style_tags", [])) for item in candidate_items
                            )
                        )
                    ),
                }
            )

    if onepieces:
        for dress, shoe in itertools.product(onepieces, shoes):
            candidate_items = [dress, shoe]
            if outers:
                outer = max(
                    outers,
                    key=lambda item: _season_alignment(item.get("season", []), profile.get("season", [])),
                )
                candidate_items.append(outer)
            score = _score_outfit(candidate_items, profile)
            combos.append(
                {
                    "items": candidate_items,
                    "score": score,
                    "style_tags": sorted(
                        set(
                            itertools.chain.from_iterable(
                                _normalise_tags(item.get("style_tags", [])) for item in candidate_items
                            )
                        )
                    ),
                }
            )

    top_combos = sorted(combos, key=lambda combo: combo["score"], reverse=True)[:max_results]

    formatted: List[dict] = []
    for idx, combo in enumerate(top_combos, start=1):
        title = f"코디 #{idx} | 점수 {combo['score']:.2f}"
        description = ", ".join(item.get("name", "") for item in combo["items"] if item.get("name"))
        formatted.append(
            {
                "title": title,
                "description": description,
                "items": [item.to_dict() for item in combo["items"]],
                "score": combo["score"],
                "style_tags": combo["style_tags"],
            }
        )

    return formatted


def _category_gap_score(inventory_df: pd.DataFrame, category: str) -> float:
    count = int(inventory_df[inventory_df["category"] == category].shape[0])
    if count == 0:
        return 1.0
    if count == 1:
        return 0.7
    if count == 2:
        return 0.4
    return 0.1


def _budget_score(price_krw: int, budget_manwon: Optional[int]) -> float:
    if not budget_manwon:
        return 0.5
    budget_krw = budget_manwon * 10000
    if price_krw <= budget_krw:
        return 1.0
    if price_krw <= budget_krw * 1.3:
        return 0.6
    return 0.2


def _best_inventory_matches(
    inventory_df: pd.DataFrame,
    category_requirements: List[str],
    profile: dict,
) -> List[pd.Series]:
    matches: List[pd.Series] = []
    for category in category_requirements:
        candidates = _inventory_by_category(inventory_df, category)
        if not candidates:
            continue
        ranked = sorted(
            candidates,
            key=lambda item: (
                _style_alignment(item.get("style_tags", []), profile.get("style_preferences", [])),
                _season_alignment(item.get("season", []), profile.get("season", [])),
            ),
            reverse=True,
        )
        matches.append(ranked[0])
    return matches


def _build_catalog_outfit(
    catalog_item: dict,
    inventory_df: pd.DataFrame,
    profile: dict,
) -> List[dict]:
    required = []
    if catalog_item["category"] == "상의":
        required = ["바지", "신발"]
    elif catalog_item["category"] == "바지":
        required = ["상의", "신발"]
    elif catalog_item["category"] == "신발":
        required = ["상의", "바지"]
    elif catalog_item["category"] == "아우터":
        required = ["상의", "바지", "신발"]
    elif catalog_item["category"] == "모자":
        required = ["상의", "바지", "신발"]
    else:
        required = ["상의", "바지", "신발"]

    supporting = _best_inventory_matches(inventory_df, required, profile)
    outfit_items = [catalog_item] + [item.to_dict() for item in supporting if item is not None]
    return outfit_items


def wishlist_suggestions(
    inventory_df: pd.DataFrame,
    profile: dict,
    *,
    limit_total: int = 120,
    per_category_cap: int | None = None,
    include_static: bool = True,
    include_musinsa: bool = True,
    include_kream: bool = True,
    musinsa_limit: int | None = None,
    kream_limit: int | None = None,
    musinsa_cookie: str | None = None,
    kream_cookie: str | None = None,
    refresh_static: bool = False,
) -> Tuple[Dict[str, List[dict]], Dict[str, object]]:
    """Recommend new items the user can consider purchasing.

    Returns a tuple ``(recommendations, meta)`` where ``meta`` contains additional
    diagnostic information such as fetch errors and source counts.
    """

    limit_total = max(int(limit_total), 1)

    musinsa_fetch_limit = musinsa_limit if musinsa_limit is not None else limit_total
    kream_fetch_limit = kream_limit if kream_limit is not None else limit_total

    catalog_data, errors = marketplace.load_catalog(
        include_static=include_static,
        include_musinsa=include_musinsa,
        include_kream=include_kream,
        musinsa_limit=musinsa_fetch_limit,
        kream_limit=kream_fetch_limit,
        musinsa_cookie=musinsa_cookie,
        kream_cookie=kream_cookie,
        include_meta=True,
        refresh_static=refresh_static,
    )

    catalog: List[dict] = catalog_data if isinstance(catalog_data, list) else []

    style_pref = profile.get("style_preferences", [])
    seasons = profile.get("season", [])

    scored_items = []
    source_counts: Dict[str, int] = {}
    for item in catalog:
        source = item.get("source", "static")
        source_counts[source] = source_counts.get(source, 0) + 1

        style_score = _style_alignment(item.get("style_tags", []), style_pref)
        gap_score = _category_gap_score(inventory_df, item.get("category", ""))
        season_score = _season_alignment(item.get("season", []), seasons)
        budget_score = _budget_score(int(item.get("price_krw", 0) or 0), profile.get("budget"))
        total_score = 0.4 * style_score + 0.3 * gap_score + 0.2 * season_score + 0.1 * budget_score

        scored_items.append(
            {
                "item": item,
                "score": round(total_score, 3),
                "style_score": style_score,
                "gap_score": gap_score,
                "season_score": season_score,
                "budget_score": budget_score,
            }
        )

    buckets: Dict[str, List[dict]] = {}
    for entry in scored_items:
        category = entry["item"].get("category", "기타")
        buckets.setdefault(category, []).append(entry)

    if per_category_cap is None and buckets:
        per_category_cap = max(10, -(-limit_total // len(buckets)))  # ceiling division
    elif per_category_cap is None:
        per_category_cap = limit_total

    recommendations: Dict[str, List[dict]] = {}
    total_selected = 0
    for category, items in buckets.items():
        ordered = sorted(items, key=lambda x: x["score"], reverse=True)
        selected = ordered[:per_category_cap]
        total_selected += len(selected)
        recommendations[category] = []
        for entry in selected:
            catalog_item = entry["item"]
            outfits = _build_catalog_outfit(catalog_item, inventory_df, profile)
            recommendations[category].append(
                {
                    "name": catalog_item.get("name"),
                    "score": entry["score"],
                    "reason": _build_reason(entry),
                    "image_url": catalog_item.get("image_url"),
                    "product_url": catalog_item.get("product_url"),
                    "price_krw": catalog_item.get("price_krw"),
                    "style_tags": catalog_item.get("style_tags", []),
                    "season": catalog_item.get("season", []),
                    "outfit_example": outfits,
                    "source": catalog_item.get("source", "static"),
                }
            )

    meta = {
        "errors": errors,
        "source_counts": source_counts,
        "total_candidates": len(scored_items),
        "total_selected": total_selected,
        "per_category_cap": per_category_cap,
    }

    return recommendations, meta


def _build_reason(entry: dict) -> str:
    reasons = []
    if entry.get("gap_score", 0) >= 0.7:
        reasons.append("옷장에 부족한 카테고리")
    if entry.get("style_score", 0) >= 0.6:
        reasons.append("선호 스타일과 잘 맞아요")
    if entry.get("season_score", 0) >= 0.6:
        seasons = ", ".join(_normalise_tags(entry["item"].get("season", [])))
        reasons.append(f"{seasons} 시즌 활용도 높음")
    if entry.get("budget_score", 0) >= 0.6:
        reasons.append("예산 범위에 적합")
    if not reasons:
        reasons.append("스타일 포인트를 더해줄 아이템")
    return " · ".join(reasons)


