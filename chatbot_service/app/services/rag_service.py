from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.llm.factory import (
    ChatModelConfig,
    EmbeddingConfig,
    create_chat_model,
    create_embedding,
)

from ..application.chat.ports import ActivityCallback
from ..application.chat.use_cases import ChatUseCase
from ..guards.output_guard import OutputGuard
from ..guards.prompt_guard import PromptGuard
from ..guards.retrieved_content_guard import RetrievedContentGuard
from ..infrastructure.graph.langgraph_chat import LangGraphChatWorkflow
from ..infrastructure.llm.answer_generator import LLMAnswerGenerator
from ..infrastructure.llm.planner import LLMQueryPlanner
from ..infrastructure.tools.content_posts import ContentPostQueryAdapter
from ..infrastructure.tools.vector_search import VectorSearchAdapter
from ..vector_store import VectorStore
from .content_post_client import ContentPostClient
from .context_builder import ContextBuilder
from .conversation_memory import (
    ConversationMemoryService,
    ConversationMessage,
    StoredConversationMemory,
)


@dataclass(slots=True)
class ChatResponse:
    """채팅 응답."""

    answer: str
    sources: list[dict]
    agent: dict[str, Any]
    guard: dict[str, Any]
    memory: dict[str, Any]


class RAGService:
    """기존 API 호환을 유지하는 LangGraph 기반 채팅 서비스."""

    def __init__(
        self,
        llm_config: ChatModelConfig,
        embedding_config: EmbeddingConfig,
        vector_store: VectorStore,
        *,
        default_top_k: int,
        default_score_threshold: float,
    ) -> None:
        llm = create_chat_model(llm_config)
        embeddings = create_embedding(embedding_config)

        prompt_guard = PromptGuard()
        output_guard = OutputGuard()
        conversation_memory = ConversationMemoryService(
            llm,
            prompt_guard,
        )

        workflow = LangGraphChatWorkflow(
            prompt_guard=prompt_guard,
            output_guard=output_guard,
            memory_service=conversation_memory,
            planner=LLMQueryPlanner(llm),
            post_query=ContentPostQueryAdapter(ContentPostClient.from_env()),
            semantic_search=VectorSearchAdapter(
                embeddings=embeddings,
                embedding_model_name=embedding_config.model,
                vector_store=vector_store,
                context_builder=ContextBuilder(RetrievedContentGuard()),
                default_top_k=default_top_k,
                default_score_threshold=default_score_threshold,
            ),
            answer_generator=LLMAnswerGenerator(llm),
        )
        self._chat_use_case = ChatUseCase(workflow)
        self._conversation_memory = conversation_memory

    def chat(
        self,
        query: str,
        *,
        messages: list[ConversationMessage] | None = None,
        stored_memory: StoredConversationMemory | None = None,
        on_activity: ActivityCallback | None = None,
    ) -> ChatResponse:
        result = self._chat_use_case.chat(
            query=query,
            messages=messages,
            stored_memory=stored_memory,
            on_activity=on_activity,
        )
        return ChatResponse(
            answer=result.answer,
            sources=result.sources,
            agent=result.agent,
            guard=result.guard,
            memory=result.memory,
        )

    def compress_session_context(
        self,
        messages: list[ConversationMessage],
    ) -> tuple[str, int]:
        """세션 메시지를 백그라운드 저장용 summary로 압축한다."""
        return self._conversation_memory.compress_for_storage(messages)
