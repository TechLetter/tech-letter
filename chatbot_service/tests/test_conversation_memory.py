from __future__ import annotations

from dataclasses import dataclass

from chatbot_service.app.guards.prompt_guard import PromptGuard
from chatbot_service.app.services.conversation_memory import (
    ConversationMemoryService,
    ConversationMessage,
    StoredConversationMemory,
)


@dataclass
class FakeLLMResponse:
    content: str


class FakeLLM:
    def invoke(self, messages):
        return FakeLLMResponse(content="현재 질문")


def _build_messages(count: int) -> list[ConversationMessage]:
    return [
        ConversationMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=f"message {index}",
        )
        for index in range(count)
    ]


def test_build_uses_stored_summary_even_when_latest_compression_failed() -> None:
    service = ConversationMemoryService(FakeLLM(), PromptGuard())

    memory = service.build(
        "현재 질문",
        _build_messages(20),
        StoredConversationMemory(
            summary="기존 압축 요약",
            covered_message_count=12,
            status="failed",
        ),
    )

    assert memory.compressed
    assert memory.compression_failed
    assert memory.summary == "기존 압축 요약"
    assert memory.summary_message_count == 12
    assert memory.status == "failed"
