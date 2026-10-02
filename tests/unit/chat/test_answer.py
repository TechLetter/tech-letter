"""답변 생성 — 프롬프트와 입력 구성."""

from __future__ import annotations

from techletter.chat.agent.answer import AnswerGenerator, build_post_context
from techletter.chat.agent.prompts import (
    ANSWER_SYSTEM_PROMPT,
    BRIEF_ANSWER_SYSTEM_PROMPT,
    NO_MATCH_ANSWER,
)
from techletter.chat.agent.state import PostRecord, ToolResult
from techletter.chat.memory import Turn


class FakeLlm:
    def __init__(self, reply: str = "답") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def candidates(self, purpose):
        return ["auto/a", "auto/b", "auto/c", "auto/d"]

    async def complete(self, purpose, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        return self.reply, "used-model"


def found(context: str = "[1] 제목 — Alpha") -> ToolResult:
    return ToolResult(status="ok", context=context)


async def test_the_answer_sees_history_posts_and_question_in_order() -> None:
    llm = FakeLlm()

    await AnswerGenerator(llm).answer(  # type: ignore[arg-type]
        "보안은?", found(), [Turn("user", "MCP 사례"), Turn("assistant", "답 [1]")]
    )

    call = llm.calls[0]
    assert call["system"] == ANSWER_SYSTEM_PROMPT
    user = call["user"]
    assert user.index("[이전 대화]") < user.index("[글]") < user.index("[질문]")
    assert "user: MCP 사례" in user


async def test_long_previous_answers_are_clipped() -> None:
    llm = FakeLlm()

    await AnswerGenerator(llm).answer("q", found(), [Turn("assistant", "가" * 5000)])  # type: ignore[arg-type]

    assert "가" * 601 not in llm.calls[0]["user"]


async def test_an_empty_reply_becomes_no_match() -> None:
    answer, _ = await AnswerGenerator(FakeLlm("  ")).answer("q", found(), [])  # type: ignore[arg-type]

    assert answer == NO_MATCH_ANSWER


async def test_a_chosen_model_goes_first_within_the_attempt_limit() -> None:
    llm = FakeLlm()

    await AnswerGenerator(llm).answer("q", found(), [], model_id="auto/b")  # type: ignore[arg-type]

    assert llm.calls[0]["candidates"] == ["auto/b", "auto/a", "auto/c"]


async def test_the_search_summary_uses_the_brief_prompt() -> None:
    llm = FakeLlm()

    await AnswerGenerator(llm).brief("Kafka", found("[Post 1] ..."))  # type: ignore[arg-type]

    assert llm.calls[0]["system"] == BRIEF_ANSWER_SYSTEM_PROMPT
    assert "[Post 1]" in llm.calls[0]["user"]


def test_the_prompt_names_the_no_match_reply() -> None:
    assert NO_MATCH_ANSWER in ANSWER_SYSTEM_PROMPT


def test_summary_context_skips_the_body() -> None:
    post = PostRecord(
        id="1",
        title="t",
        link="l",
        blog_name="b",
        published_at="",
        summary="요약",
        plain_text="본문",
    )

    context = build_post_context([post], summaries_only=True)

    assert "요약" in context
    assert "본문" not in context
