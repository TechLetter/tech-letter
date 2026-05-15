from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from ...domain.chat.schemas import ChatPlan, ChatResult, PostConstraints, ToolResult
from ...services.conversation_memory import (
    ConversationMessage,
    ConversationMemoryContext,
    StoredConversationMemory,
)


ActivityCallback = Callable[[dict[str, str]], None]


@dataclass(slots=True)
class ChatInput:
    query: str
    messages: list[ConversationMessage]
    stored_memory: StoredConversationMemory | None = None
    on_activity: ActivityCallback | None = None


class ChatWorkflowPort(Protocol):
    def run(self, chat_input: ChatInput) -> ChatResult: ...


class QueryPlannerPort(Protocol):
    def plan(
        self,
        *,
        query: str,
        memory: ConversationMemoryContext,
        now: datetime,
    ) -> ChatPlan: ...


class PostQueryPort(Protocol):
    def list_posts(self, constraints: PostConstraints) -> ToolResult: ...

    def hydrate_content(self, posts: list) -> list: ...


class SemanticSearchPort(Protocol):
    def search(self, query: str, constraints: PostConstraints | None = None) -> ToolResult: ...


class AnswerGeneratorPort(Protocol):
    def generate(
        self,
        *,
        query: str,
        plan: ChatPlan,
        tool_result: ToolResult,
        memory: ConversationMemoryContext,
    ) -> str: ...
