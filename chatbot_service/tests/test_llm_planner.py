from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from chatbot_service.app.infrastructure.llm.planner import LLMQueryPlanner
from chatbot_service.app.services.conversation_memory import ConversationMemoryContext


@dataclass
class FakeResponse:
    content: str


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, messages):
        return FakeResponse(self.content)


def _memory() -> ConversationMemoryContext:
    return ConversationMemoryContext(
        used=False,
        compressed=False,
        compression_failed=False,
        strategy="none",
        summary="",
        recent_messages=[],
        summary_message_count=0,
        recent_message_count=0,
        history_message_count=0,
        rewritten_query="오늘 하루 포스트 내용 찾아줘",
        rewritten=False,
        status="none",
    )


def test_planner_parses_structured_post_plan() -> None:
    planner = LLMQueryPlanner(
        FakeLLM(
            """
            {
              "task": "summarize_posts",
              "constraints": {
                "published_from": "2026-05-14T00:00:00+09:00",
                "published_to": "2026-05-15T00:00:00+09:00",
                "blog_name": null,
                "categories": [],
                "tags": [],
                "limit": 5
              },
              "strict_scope": true,
              "needs_content": true,
              "reason": "오늘 포스트 내용 요청"
            }
            """
        )
    )

    plan = planner.plan(
        query="오늘 하루 포스트 내용 찾아줘",
        memory=_memory(),
        now=datetime(2026, 5, 14, 22, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert plan.task == "summarize_posts"
    assert plan.strict_scope
    assert plan.needs_content
    assert plan.constraints.limit == 5
    assert plan.constraints.published_from is not None
    assert plan.constraints.published_to is not None
