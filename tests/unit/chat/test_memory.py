"""대화 맥락 구성."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from techletter.chat.memory import MemoryBuilder
from techletter.chat.models import ChatMessage
from techletter.settings import ChatSettings


class FakeLlm:
    """`complete`가 정해진 답을 준다. 예외를 주면 던진다."""

    def __init__(self, reply: str | Exception = "재작성된 질문") -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.systems: list[str] = []

    async def complete(self, purpose, system, user, **kwargs):
        self.prompts.append(user)
        self.systems.append(system)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply, "test-model"


@pytest.fixture
def settings() -> ChatSettings:
    return ChatSettings(memory_recent_messages=4)


def turns(count: int, prefix: str = "m") -> list[ChatMessage]:
    return [
        ChatMessage(role="user" if index % 2 == 0 else "assistant", content=f"{prefix}{index}")
        for index in range(count)
    ]


async def test_an_empty_history_is_an_empty_context(settings: ChatSettings) -> None:
    llm = FakeLlm()

    context = await MemoryBuilder(settings).build("질문", [])  # type: ignore[arg-type]

    assert context.recent == []
    assert context.used is False
    assert llm.prompts == []


async def test_building_never_calls_the_llm(settings: ChatSettings) -> None:
    """예전에는 후속 질문마다 LLM으로 질문을 다시 썼다. 이제 호출이 없다."""
    llm = FakeLlm()

    await MemoryBuilder(settings).build("그럼 보안은?", turns(6))  # type: ignore[arg-type]

    assert llm.prompts == []


async def test_only_the_recent_window_is_kept(settings: ChatSettings) -> None:
    context = await MemoryBuilder(settings).build("q", turns(10))  # type: ignore[arg-type]

    assert [turn.content for turn in context.recent] == ["m6", "m7", "m8", "m9"]
    assert context.history_message_count == 10


async def test_the_previous_question_and_sources_are_carried(settings: ChatSettings) -> None:
    messages = [
        ChatMessage(role="user", content="vLLM 서빙 사례"),
        ChatMessage(
            role="assistant",
            content="답",
            metadata={"sources": [{"post_id": "p1"}, {"post_id": "p2"}, {"title": "id 없음"}]},
        ),
    ]

    context = await MemoryBuilder(settings).build("거기서 KV 캐시는?", messages)  # type: ignore[arg-type]

    assert context.previous_query == "vLLM 서빙 사례"
    assert context.previous_source_ids == ["p1", "p2"]


async def test_code_blocks_keep_their_line_breaks(settings: ChatSettings) -> None:
    code = "```python\nprint(1)\n```"

    context = await MemoryBuilder(settings).build(  # type: ignore[arg-type]
        "q", [ChatMessage(role="user", content=code)]
    )

    assert context.recent[0].content == code


def test_only_user_and_assistant_roles_are_accepted() -> None:
    with pytest.raises(ValidationError):
        ChatMessage(role="system", content="x")  # type: ignore[arg-type]


async def test_long_messages_are_clipped(settings: ChatSettings) -> None:
    settings.memory_max_message_chars = 5

    context = await MemoryBuilder(settings).build(  # type: ignore[arg-type]
        "q", [ChatMessage(role="user", content="가" * 50)]
    )

    assert len(context.recent[0].content) == 5


async def test_metadata_matches_the_contract(settings: ChatSettings) -> None:
    context = await MemoryBuilder(settings).build("q", turns(2))  # type: ignore[arg-type]

    assert context.to_metadata() == {
        "used": True,
        "strategy": "recent_window",
        "recent_message_count": 2,
        "history_message_count": 2,
        "status": "ready",
    }
