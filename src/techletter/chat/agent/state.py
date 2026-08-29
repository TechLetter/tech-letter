"""에이전트가 다루는 값들."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

__all__ = [
    "Activity",
    "ChatPlan",
    "ChatTask",
    "PostConstraints",
    "PostRecord",
    "Source",
    "ToolResult",
    "ToolStatus",
]

ChatTask = Literal[
    "list_posts",
    "summarize_posts",
    "answer_from_posts",
    "semantic_search_posts",
    "general_rag",
    "no_result",
]
ToolStatus = Literal["ok", "no_result", "failed"]


@dataclass(slots=True)
class PostConstraints:
    published_from: datetime | None = None
    published_to: datetime | None = None
    blog_name: str | None = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    limit: int = 10

    def has_scope(self) -> bool:
        """사용자가 범위를 못 박았는지. 그렇다면 엉뚱한 글로 대체하면 안 된다."""
        return bool(
            self.published_from
            or self.published_to
            or self.blog_name
            or self.categories
            or self.tags
        )


@dataclass(slots=True)
class ChatPlan:
    task: ChatTask = "general_rag"
    constraints: PostConstraints = field(default_factory=PostConstraints)
    strict_scope: bool = False
    needs_content: bool = False
    reason: str = ""


@dataclass(slots=True)
class PostRecord:
    id: str
    title: str
    link: str
    blog_name: str
    published_at: str
    summary: str = ""
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    plain_text: str | None = None


@dataclass(frozen=True, slots=True)
class Source:
    post_id: str
    title: str
    blog_name: str
    link: str
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "blog_name": self.blog_name,
            "link": self.link,
            "score": self.score,
        }


@dataclass(slots=True)
class ToolResult:
    status: ToolStatus = "no_result"
    posts: list[PostRecord] = field(default_factory=list)
    context: str = ""
    sources: list[Source] = field(default_factory=list)
    total: int = 0
    message: str = ""


@dataclass(frozen=True, slots=True)
class Activity:
    """진행 상황 한 줄. SSE로 그대로 흘려보낸다."""

    type: str
    label: str
    status: Literal["running", "completed", "failed"]

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "label": self.label, "status": self.status}
