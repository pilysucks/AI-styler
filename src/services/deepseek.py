"""DeepSeek API integration helpers."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Iterable, Optional, Sequence, Tuple

import requests


logger = logging.getLogger(__name__)


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-fe99ffe22e274a7eb1d2792889466969")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def is_configured() -> bool:
    """Return True if the DeepSeek API can be called safely."""

    return bool(DEEPSEEK_API_KEY and DEEPSEEK_API_URL)


def _chat_completion(messages: Sequence[dict], *, temperature: float = 0.7, max_tokens: int = 200) -> str:
    if not is_configured():
        raise RuntimeError("DeepSeek API credentials가 설정되지 않았습니다")

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = requests.post(DEEPSEEK_API_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek API 응답에 choices가 없습니다")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("DeepSeek API 응답에 content가 없습니다")

    return str(content).strip()


@lru_cache(maxsize=256)
def _cached_product_caption(key: Tuple[str, int, Tuple[str, ...], str]) -> Optional[str]:
    name, price, tags, source = key
    price_text = f"{price:,}원" if price else "가격 정보 없음"
    tags_text = ", ".join(tags) if tags else "태그 없음"
    source_text = source or "미상"

    user_prompt = (
        "다음 패션 상품을 소개하는 한 문장을 작성해 주세요. "
        "문장은 60자 이내, 한국어로 작성하고, 과장된 표현은 피합니다. "
        "상품명, 가격, 스타일 태그, 판매 채널을 자연스럽게 녹여주세요.\n"
        f"상품명: {name}\n"
        f"가격: {price_text}\n"
        f"스타일 태그: {tags_text}\n"
        f"판매 채널: {source_text}\n"
    )

    messages = [
        {
            "role": "system",
            "content": "당신은 패션 MD입니다. 간결하고 정확한 추천 문장을 제공합니다.",
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    try:
        return _chat_completion(messages, temperature=0.6, max_tokens=120)
    except Exception as exc:  # pragma: no cover - network errors handled gracefully
        logger.warning("DeepSeek caption generation failed: %s", exc)
        return None


def product_caption(
    *,
    name: str,
    price_krw: Optional[int],
    style_tags: Iterable[str],
    source: Optional[str] = None,
) -> Optional[str]:
    """Generate a short marketing caption for a product using DeepSeek."""

    key = (
        name,
        int(price_krw or 0),
        tuple(sorted({tag.strip() for tag in style_tags if tag})),
        (source or "").strip(),
    )
    return _cached_product_caption(key)


