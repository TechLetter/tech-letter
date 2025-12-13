from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from common.llm.factory import (
    ChatModelConfig,
    EmbeddingConfig,
    create_chat_model,
    create_embedding,
)
from common.llm.utils import normalize_model_name

from ..vector_store import VectorStore


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI assistant that answers questions based on technical blog content.

Follow these rules strictly:

1) Use ONLY the information in the provided context. Do not use outside knowledge.
2) If the context does not contain enough information to answer, say clearly in Korean that you cannot find relevant information.
3) Answer in Korean.
4) Write a clear and structured answer.
5) When applicable, mention sources by blog name and title (use the context items).

Context:
{context}
"""


@dataclass(slots=True)
class ChatResponse:
    """채팅 응답."""

    answer: str
    sources: list[dict]


class RAGService:
    """RAG 기반 질의응답 서비스."""

    def __init__(
        self,
        llm_config: ChatModelConfig,
        embedding_config: EmbeddingConfig,
        vector_store: VectorStore,
        *,
        default_top_k: int,
        default_score_threshold: float,
    ) -> None:
        self._vector_store = vector_store
        self._default_top_k = default_top_k
        self._default_score_threshold = default_score_threshold
        self._embedding_model_key = normalize_model_name(embedding_config.model)

        self._llm = create_chat_model(llm_config)
        self._embeddings = create_embedding(embedding_config)

    def chat(self, query: str) -> ChatResponse:
        """사용자 질문에 대해 RAG 기반 답변을 생성한다."""

        logger.info("processing chat query: %s", query[:100])

        # 1. 쿼리 임베딩 생성
        try:
            query_vector = self._embeddings.embed_query(query)
        except Exception:  # noqa: BLE001
            logger.exception("failed to embed query")
            raise

        # 2. Vector DB에서 관련 문서 검색
        try:
            search_results = self._vector_store.search(
                query_vector,
                self._embedding_model_key,
                limit=self._default_top_k,
                score_threshold=self._default_score_threshold,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to search vector store")
            raise

        if not search_results:
            logger.info("no relevant documents found for query")
            return ChatResponse(
                answer="죄송합니다. 관련 정보를 찾을 수 없습니다. 다른 질문을 해주세요.",
                sources=[],
            )

        # 3. 컨텍스트 구성
        context_parts: list[str] = []
        sources: list[dict] = []

        for idx, result in enumerate(search_results, 1):
            chunk_text = result.get("chunk_text", "")
            title = result.get("title", "Unknown")
            blog_name = result.get("blog_name", "Unknown")
            link = result.get("link", "")

            context_parts.append(f"[{idx}] {title} ({blog_name})\n{chunk_text}")
            sources.append(
                {
                    "title": title,
                    "blog_name": blog_name,
                    "link": link,
                    "score": result.get("score", 0),
                }
            )

        context = "\n\n".join(context_parts)

        # 4. LLM으로 답변 생성
        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT.format(context=context)),
                HumanMessage(content=query),
            ]
            response = self._llm.invoke(messages)
            answer = str(response.content)
        except Exception:  # noqa: BLE001
            logger.exception("failed to generate LLM response")
            raise

        logger.info(
            "generated response with %d sources, answer_len=%d",
            len(sources),
            len(answer),
        )

        return ChatResponse(answer=answer, sources=sources)
