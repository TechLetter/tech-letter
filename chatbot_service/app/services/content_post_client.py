from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(slots=True)
class PostListParams:
    page: int = 1
    page_size: int = 10
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    blog_name: str | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    status_ai_summarized: bool | None = None
    status_embedded: bool | None = None


@dataclass(slots=True)
class PostItem:
    id: str
    title: str
    link: str
    blog_name: str
    published_at: str
    summary: str
    categories: list[str]
    tags: list[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PostItem":
        summary_payload = payload.get("aisummary") or {}
        return cls(
            id=str(payload.get("id") or ""),
            title=str(payload.get("title") or ""),
            link=str(payload.get("link") or ""),
            blog_name=str(payload.get("blog_name") or ""),
            published_at=str(payload.get("published_at") or ""),
            summary=str(summary_payload.get("summary") or ""),
            categories=[
                str(category) for category in summary_payload.get("categories") or []
            ],
            tags=[str(tag) for tag in summary_payload.get("tags") or []],
        )


@dataclass(slots=True)
class PostListResult:
    total: int
    items: list[PostItem]


@dataclass(slots=True)
class ContentPostClient:
    base_url: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "ContentPostClient":
        return cls(
            base_url=os.getenv(
                "CONTENT_SERVICE_BASE_URL", "http://content_service:8001"
            ).rstrip("/")
        )

    def list_posts(self, params: PostListParams) -> PostListResult:
        query: list[tuple[str, str]] = [
            ("page", str(max(params.page, 1))),
            ("page_size", str(max(min(params.page_size, 100), 1))),
        ]
        query.extend(("categories", category) for category in params.categories)
        query.extend(("tags", tag) for tag in params.tags)

        if params.blog_name:
            query.append(("blog_name", params.blog_name))
        if params.published_from:
            query.append(("published_from", params.published_from.isoformat()))
        if params.published_to:
            query.append(("published_to", params.published_to.isoformat()))
        if params.status_ai_summarized is not None:
            query.append(
                ("status_ai_summarized", str(params.status_ai_summarized).lower())
            )
        if params.status_embedded is not None:
            query.append(("status_embedded", str(params.status_embedded).lower()))

        url = f"{self.base_url}/api/v1/posts?{urlencode(query)}"
        with urlopen(url, timeout=self.timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))

        items = [
            PostItem.from_payload(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        return PostListResult(total=int(payload.get("total") or 0), items=items)
