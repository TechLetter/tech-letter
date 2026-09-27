"""답변 생성 — 검색 AI 요약은 짧은 프롬프트, 챗봇은 깊은 프롬프트."""

from __future__ import annotations

import json

from techletter.chat.agent.answer import AnswerGenerator, build_post_context
from techletter.chat.agent.prompts import ANSWER_SYSTEM_PROMPT, BRIEF_ANSWER_SYSTEM_PROMPT
from techletter.chat.agent.state import ChatPlan, PostRecord, ToolResult


class FakeLlm:
    def __init__(self) -> None:
        self.systems: list[str] = []
        self.users: list[dict] = []

    async def complete(self, role, system, user, candidates=None):
        self.systems.append(system)
        self.users.append(json.loads(user))
        return "답변", "model-a"

    async def candidates(self, role):
        return []


def post(index: int) -> PostRecord:
    return PostRecord(
        id=f"id{index}",
        title=f"제목{index}",
        link=f"https://x.test/{index}",
        blog_name="Alpha",
        published_at="2026-09-01T00:00:00Z",
        summary=f"요약{index}",
        plain_text=f"본문{index}",
    )


async def test_the_search_summary_uses_the_brief_prompt() -> None:
    llm = FakeLlm()
    result = ToolResult(status="ok", posts=[post(1)], context="ctx")

    await AnswerGenerator(llm).generate(  # type: ignore[arg-type]
        "kafka", ChatPlan(task="answer_from_posts", brief=True), result, {}
    )

    assert llm.systems == [BRIEF_ANSWER_SYSTEM_PROMPT]


async def test_the_chatbot_uses_the_in_depth_prompt() -> None:
    llm = FakeLlm()
    result = ToolResult(status="ok", posts=[post(1)], context="ctx")

    await AnswerGenerator(llm).generate(  # type: ignore[arg-type]
        "kafka", ChatPlan(task="general_rag"), result, {}
    )

    assert llm.systems == [ANSWER_SYSTEM_PROMPT]


def test_summary_context_skips_the_body() -> None:
    brief = build_post_context([post(1), post(2)], summaries_only=True)
    full = build_post_context([post(1)])

    assert "[Post 2]" in brief
    assert "요약1" in brief
    assert "본문1" not in brief
    assert "본문1" in full
