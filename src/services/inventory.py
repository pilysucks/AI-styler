"""Inventory management utilities for the AI Styler Streamlit app."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_FILE = PROJECT_ROOT / "data" / "inventory.json"
UPLOAD_DIR = PROJECT_ROOT / "assets" / "uploads"


CATEGORY_OPTIONS: List[str] = [
    "상의",
    "바지",
    "아우터",
    "신발",
    "모자",
    "원피스",
    "스커트",
    "액세서리",
    "기타",
]

SEASON_OPTIONS: List[str] = ["봄", "여름", "가을", "겨울", "사계절"]


def _ensure_directories() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _empty_inventory() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "item_id",
            "name",
            "category",
            "color",
            "season",
            "style_tags",
            "image_path",
            "notes",
            "created_at",
        ]
    )


def _normalise_tags(raw_tags: Optional[Iterable[str]]) -> List[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        tags = [tag.strip() for tag in raw_tags.split(",")]
    else:
        tags = [str(tag).strip() for tag in raw_tags]
    return [tag for tag in tags if tag]


def load_inventory() -> pd.DataFrame:
    """Load inventory data as a pandas DataFrame."""

    _ensure_directories()
    if not INVENTORY_FILE.exists():
        return _empty_inventory()

    with INVENTORY_FILE.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if not data:
        return _empty_inventory()

    df = pd.DataFrame(data)
    if "style_tags" in df.columns:
        df["style_tags"] = df["style_tags"].apply(_normalise_tags)
    if "season" in df.columns:
        df["season"] = df["season"].apply(lambda x: _normalise_tags(x) or ["사계절"])
    return df


def save_inventory(df: pd.DataFrame) -> None:
    """Persist the inventory dataframe to disk."""

    _ensure_directories()
    serialisable = df.fillna("").to_dict(orient="records")
    for record in serialisable:
        record["style_tags"] = _normalise_tags(record.get("style_tags"))
        record["season"] = _normalise_tags(record.get("season")) or ["사계절"]
    with INVENTORY_FILE.open("w", encoding="utf-8") as fp:
        json.dump(serialisable, fp, ensure_ascii=False, indent=2)


def add_item(
    name: str,
    category: str,
    color: str,
    season: Optional[Iterable[str]] = None,
    style_tags: Optional[Iterable[str]] = None,
    image_file=None,
    notes: str = "",
) -> dict:
    """Add a new item to the inventory and return the created record."""

    df = load_inventory()
    item_id = uuid.uuid4().hex[:8]
    season_tags = _normalise_tags(season) or ["사계절"]
    style_list = _normalise_tags(style_tags)

    image_path = None
    if image_file is not None:
        suffix = Path(image_file.name).suffix or ".png"
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{item_id}{suffix}"
        destination = UPLOAD_DIR / filename
        with destination.open("wb") as output:
            output.write(image_file.getbuffer())
        image_path = str(destination.relative_to(PROJECT_ROOT))

    record = {
        "item_id": item_id,
        "name": name.strip(),
        "category": category.strip() if category else "기타",
        "color": color.strip() if color else "",
        "season": season_tags,
        "style_tags": style_list,
        "image_path": image_path,
        "notes": notes.strip(),
        "created_at": datetime.utcnow().isoformat(),
    }

    df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
    save_inventory(df)
    return record


def remove_item(item_id: str) -> None:
    """Remove item from inventory by its identifier."""

    df = load_inventory()
    if df.empty:
        return
    df = df[df["item_id"] != item_id]
    save_inventory(df)


def inventory_summary(df: pd.DataFrame) -> dict:
    """Return quick stats to show in the UI."""

    if df.empty:
        return {"total": 0, "by_category": {}}

    summary = {
        "total": int(df.shape[0]),
        "by_category": df.groupby("category")["item_id"].count().to_dict(),
    }
    return summary


def style_tag_options() -> List[str]:
    """Return curated list of style tags inspired by Korean Instagram trends."""

    return [
        "미니멀",
        "스트릿",
        "캐주얼",
        "포멀",
        "페미닌",
        "요즘것",
        "빈티지",
        "아메카지",
        "하이틴",
        "테크웨어",
        "시티보이",
    ]


def season_options() -> List[str]:
    return SEASON_OPTIONS


def category_options() -> List[str]:
    return CATEGORY_OPTIONS


def to_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a dataframe formatted for Streamlit display."""

    if df.empty:
        return _empty_inventory()

    display_df = df.copy()
    display_df["season"] = display_df["season"].apply(lambda x: ", ".join(_normalise_tags(x)))
    display_df["style_tags"] = display_df["style_tags"].apply(lambda x: ", ".join(_normalise_tags(x)))
    return display_df


