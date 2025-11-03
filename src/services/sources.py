"""External catalog fetchers for Musinsa and KREAM."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


PRICE_PATTERN = re.compile(r"(\d+[\d,]*)")


def _parse_cookie_header(cookie_header: str | None) -> Dict[str, str]:
    if not cookie_header:
        return {}
    cookies: Dict[str, str] = {}
    for chunk in cookie_header.split(";"):
        if "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value
    return cookies


def _create_session(cookie_header: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if cookie_header:
        session.cookies.update(_parse_cookie_header(cookie_header))
    return session


def _safe_int(value: str | None) -> Optional[int]:
    if not value:
        return None
    match = PRICE_PATTERN.search(value)
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    try:
        return int(digits)
    except ValueError:
        return None


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _normalise_category(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return "기타"
    keywords = {
        "상의": "상의",
        "탑": "상의",
        "셔츠": "상의",
        "티셔츠": "상의",
        "바지": "바지",
        "팬츠": "바지",
        "데님": "바지",
        "진": "바지",
        "아우터": "아우터",
        "재킷": "아우터",
        "코트": "아우터",
        "점퍼": "아우터",
        "신발": "신발",
        "슈즈": "신발",
        "스니커": "신발",
        "모자": "모자",
        "캡": "모자",
        "버킷": "모자",
        "드레스": "원피스",
        "원피스": "원피스",
        "스커트": "스커트",
        "악세": "액세서리",
        "액세서리": "액세서리",
        "백": "액세서리",
        "가방": "액세서리",
    }
    for keyword, category in keywords.items():
        if keyword in text:
            return category
    return "기타"


def _deduplicate(items: Iterable[dict]) -> List[dict]:
    seen: set[str] = set()
    unique: List[dict] = []
    for item in items:
        key = item.get("product_url") or item.get("source_id")
        if not key:
            unique.append(item)
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def fetch_musinsa_catalog(
    *,
    limit: int = 120,
    cookie_header: Optional[str] = None,
    category_codes: Optional[Iterable[Tuple[str, str]]] = None,
    delay: float = 0.3,
) -> List[dict]:
    """Fetch product metadata from Musinsa ranking pages.

    Args:
        limit: Maximum number of products to return.
        cookie_header: Optional cookie string from an authenticated Musinsa session.
        category_codes: Iterable of tuples ``(category_code, label)``. Defaults to
            a curated set of apparel categories.
        delay: Seconds to sleep between page requests to be polite.
    """

    default_categories = [
        ("001", "상의"),
        ("002", "바지"),
        ("003", "아우터"),
        ("004", "원피스"),
        ("007", "스커트"),
        ("005", "신발"),
        ("020", "모자"),
        ("022", "액세서리"),
    ]
    categories = list(category_codes or default_categories)

    session = _create_session(cookie_header)
    results: List[dict] = []

    for category_code, label in categories:
        page = 1
        category_results: List[dict] = []
        while len(category_results) < limit:
            params = {
                "period": "now",
                "viewFlag": "BOX",
                "page": page,
                "mainCategory": category_code,
                "subCategory": "",
                "leafCategory": "",
                "price": "",
            }
            url = "https://search.musinsa.com/ranking/best"
            try:
                response = session.get(url, params=params, timeout=10)
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.warning("Musinsa request failed for %s page %s: %s", category_code, page, exc)
                break

            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("li.li_box") or soup.select("li.li_box_new")
            if not items:
                logger.debug("No items found on Musinsa page %s for category %s", page, category_code)
                break

            for node in items:
                link = node.select_one("p.list_img a") or node.select_one("div.img-block a")
                name_node = node.select_one("p.list_info a") or node.select_one("p.item_title a")
                image_node = node.select_one("img")
                price_node = node.select_one("p.price") or node.select_one("span.txt_price")
                category_hint = (
                    node.get("data-category")
                    or node.get("data-goods-no")
                    or _clean_text(node.select_one("p.item_category").get_text() if node.select_one("p.item_category") else "")
                )

                if not link or not name_node:
                    continue

                product_url = link.get("href")
                if product_url and product_url.startswith("//"):
                    product_url = f"https:{product_url}"
                if product_url and product_url.startswith("/"):
                    product_url = f"https://www.musinsa.com{product_url}"

                name = _clean_text(name_node.get_text())
                price = _safe_int(price_node.get_text() if price_node else None)
                image_url = None
                if image_node:
                    image_url = image_node.get("data-original") or image_node.get("data-src") or image_node.get("src")
                    if image_url and image_url.startswith("//"):
                        image_url = f"https:{image_url}"

                normalized_category = label
                if category_hint:
                    normalized_category = _normalise_category(category_hint)
                    if normalized_category == "기타":
                        normalized_category = label

                category_results.append(
                    {
                        "name": name,
                        "category": normalized_category,
                        "price_krw": price,
                        "image_url": image_url,
                        "product_url": product_url,
                        "source": "musinsa",
                        "source_id": node.get("data-goods-code") or node.get("data-goods-no"),
                        "style_tags": [],
                        "season": ["사계절"],
                    }
                )

            page += 1
            if delay:
                time.sleep(delay)
            if page > 20:  # safety stop
                break

        results.extend(category_results[:limit])
        if len(results) >= limit:
            break

    return _deduplicate(results)[:limit]


def _recursive_find_products(node) -> List[dict]:
    found: List[dict] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "products" in current and isinstance(current["products"], list):
                for item in current["products"]:
                    if isinstance(item, dict) and item:
                        found.append(item)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def fetch_kream_catalog(
    *,
    limit: int = 120,
    cookie_header: Optional[str] = None,
    search_paths: Optional[Iterable[Tuple[str, str]]] = None,
    delay: float = 0.4,
) -> List[dict]:
    """Fetch product metadata from KREAM search pages using embedded Next.js data."""

    default_paths = [
        ("https://kream.co.kr/search?category_id=18&sort=popular", "신발"),
        ("https://kream.co.kr/search?category_id=33&sort=popular", "상의"),
        ("https://kream.co.kr/search?category_id=34&sort=popular", "바지"),
        ("https://kream.co.kr/search?category_id=35&sort=popular", "아우터"),
        ("https://kream.co.kr/search?category_id=36&sort=popular", "모자"),
    ]
    targets = list(search_paths or default_paths)

    session = _create_session(cookie_header)
    collected: List[dict] = []

    for url, default_category in targets:
        try:
            response = session.get(url, timeout=12)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("KREAM request failed for %s: %s", url, exc)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            logger.debug("No Next.js data found for %s", url)
            continue

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Next.js payload for %s: %s", url, exc)
            continue

        products = _recursive_find_products(data)
        if not products:
            logger.debug("No products discovered in payload for %s", url)
            continue

        for product in products:
            product_url = product.get("url") or product.get("permalink")
            if product_url and product_url.startswith("/"):
                product_url = f"https://kream.co.kr{product_url}"

            name = product.get("translated_name") or product.get("name") or product.get("title")
            name = _clean_text(name)
            if not name:
                continue

            price = product.get("lowest_ask") or product.get("price") or product.get("original_price")
            if isinstance(price, dict):
                price = price.get("amount")
            if isinstance(price, (list, tuple)):
                price = price[0] if price else None
            price_value = _safe_int(str(price)) if price else None

            image = product.get("image_url") or product.get("thumbnail_url") or product.get("image")
            if image and image.startswith("//"):
                image = f"https:{image}"
            if image and image.startswith("/"):
                image = f"https://kream.co.kr{image}"

            category_hint = product.get("category_ko_name") or product.get("category_name") or product.get("category")
            category = _normalise_category(category_hint) if category_hint else default_category
            if category == "기타":
                category = default_category

            style_tags: List[str] = []
            brand = product.get("brand_name") or product.get("brand_ko_name")
            if isinstance(brand, str) and brand:
                style_tags.append(brand.strip())

            collected.append(
                {
                    "name": name,
                    "category": category,
                    "price_krw": price_value,
                    "image_url": image,
                    "product_url": product_url,
                    "source": "kream",
                    "source_id": str(product.get("id") or product.get("product_id")) if product.get("id") else None,
                    "style_tags": style_tags,
                    "season": ["사계절"],
                }
            )

        if delay:
            time.sleep(delay)

    return _deduplicate(collected)[:limit]


def fetch_combined_catalog(
    *,
    musinsa_limit: int = 120,
    kream_limit: int = 120,
    musinsa_cookie: Optional[str] = None,
    kream_cookie: Optional[str] = None,
) -> List[dict]:
    """Convenience helper to fetch combined catalog data from both sources."""

    musinsa_items = []
    kream_items = []

    if musinsa_limit > 0:
        musinsa_items = fetch_musinsa_catalog(limit=musinsa_limit, cookie_header=musinsa_cookie)

    if kream_limit > 0:
        kream_items = fetch_kream_catalog(limit=kream_limit, cookie_header=kream_cookie)

    combined = list(musinsa_items) + list(kream_items)
    return _deduplicate(combined)



