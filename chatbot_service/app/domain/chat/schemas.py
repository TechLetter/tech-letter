from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ChatTask = Literal[
    "list_posts",
    "summarize_posts",
    "answer_from_posts",
    "semantic_search_posts",
    "general_rag",
    "no_result",
]

ToolResultStatus = Literal["ok", "no_result", "failed"]


@dataclass(slots=True)
class PostConstraints:
    published_from: datetime | None = None
    published_to: datetime | None = None
    blog_name: str | None = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    limit: int = 10

    def has_scope(self) -> bool:
        return any(
            [
                self.published_from is not None,
                self.published_to is not None,
                bool(self.blog_name),
                bool(self.categories),
                bool(self.tags),
            ]
        )


@dataclass(slots=True)
class ChatPlan:
    task: ChatTask
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


@dataclass(slots=True)
class Source:
    title: str
    blog_name: str
    link: str
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "blog_name": self.blog_name,
            "link": self.link,
            "score": self.score,
        }


@dataclass(slots=True)
class ToolResult:
    status: ToolResultStatus
    posts: list[PostRecord] = field(default_factory=list)
    context: str = ""
    sources: list[Source] = field(default_factory=list)
    total: int = 0
    message: str = ""


@dataclass(slots=True)
class ChatResult:
    answer: str
    sources: list[dict[str, Any]]
    agent: dict[str, Any]
    guard: dict[str, Any]
    memory: dict[str, Any]
