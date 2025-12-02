from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self


class EventType:
    POST_CREATED = "post.created"
    POST_SUMMARIZED = "post.summarized"


@dataclass(slots=True)
class PostCreatedEvent:
    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    blog_id: str
    blog_name: str
    title: str
    link: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            blog_id=str(data["blog_id"]),
            blog_name=str(data["blog_name"]),
            title=str(data["title"]),
            link=str(data["link"]),
        )


@dataclass(slots=True)
class PostSummarizedEvent:
    id: str
    type: str
    timestamp: str
    source: str
    version: str
    post_id: str
    link: str
    rendered_html: str
    plain_text: str
    thumbnail_url: str
    categories: list[str]
    tags: list[str]
    summary: str
    model_name: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            version=str(data.get("version", "1.0")),
            post_id=str(data["post_id"]),
            link=str(data["link"]),
            rendered_html=str(data["rendered_html"]),
            plain_text=str(data.get("plain_text", "")),
            thumbnail_url=str(data.get("thumbnail_url", "")),
            categories=list(data.get("categories", [])),
            tags=list(data.get("tags", [])),
            summary=str(data["summary"]),
            model_name=str(data["model_name"]),
        )
