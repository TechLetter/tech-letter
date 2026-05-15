from __future__ import annotations

from ...domain.chat.schemas import ChatResult
from .ports import ActivityCallback, ChatInput, ChatWorkflowPort
from ...services.conversation_memory import (
    ConversationMessage,
    StoredConversationMemory,
)


class ChatUseCase:
    def __init__(self, workflow: ChatWorkflowPort) -> None:
        self._workflow = workflow

    def chat(
        self,
        *,
        query: str,
        messages: list[ConversationMessage] | None = None,
        stored_memory: StoredConversationMemory | None = None,
        on_activity: ActivityCallback | None = None,
    ) -> ChatResult:
        return self._workflow.run(
            ChatInput(
                query=query,
                messages=messages or [],
                stored_memory=stored_memory,
                on_activity=on_activity,
            )
        )
