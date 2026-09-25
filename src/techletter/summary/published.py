"""원문 페이지에 적힌 발행일.

피드에 발행일이 없으면(Google Developers Blog) 수집 시각을 발행일로 넣어 둔다. 그대로
두면 옛 글이 오늘 글처럼 최신순 맨 위와 이번 주 트렌드에 섞인다. 본문을 가져올 때
페이지의 구조화된 날짜로 바로잡는다 — 본문 속 날짜처럼 보이는 글자는 믿지 않는다.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from techletter.core.time import utcnow

__all__ = ["extract_published_at"]

_META_KEYS = (
    ("property", "article:published_time"),
    ("property", "og:article:published_time"),
    ("itemprop", "datePublished"),
    ("name", "article:published_time"),
    ("name", "date"),
    ("name", "pubdate"),
)
_EARLIEST = datetime(2000, 1, 1, tzinfo=UTC)


def extract_published_at(html: str, now: datetime | None = None) -> datetime | None:
    """JSON-LD `datePublished` → 발행일 메타 태그 순으로 찾는다. 못 찾으면 None."""
    from bs4 import BeautifulSoup  # noqa: PLC0415

    soup = BeautifulSoup(html or "", "html.parser")
    candidates = [*_json_ld_dates(soup), *_meta_dates(soup)]
    limit = (now or utcnow()) + timedelta(days=1)
    for raw in candidates:
        parsed = _parse(raw)
        if parsed and _EARLIEST <= parsed <= limit:
            return parsed
    return None


def _json_ld_dates(soup: Any) -> list[str]:
    found: list[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (TypeError, ValueError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                value = node.get("datePublished")
                if isinstance(value, str):
                    found.append(value)
                stack.extend(v for v in node.values() if isinstance(v, dict | list))
    return found


def _meta_dates(soup: Any) -> list[str]:
    found: list[str] = []
    for attr, key in _META_KEYS:
        tag = soup.find("meta", attrs={attr: key})
        content = tag.get("content") if tag else None
        if isinstance(content, str):
            found.append(content)
    return found


def _parse(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    text = re.sub(r"Z$", "+00:00", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # 날짜만 있거나 시간대가 없으면 UTC로 본다.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
