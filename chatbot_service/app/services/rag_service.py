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

SYSTEM_PROMPT = """You are an expert Tech Blog Consultant for "Tech-Letter".
Your goal is to provide the best possible answer to developer questions based **ONLY** on the provided context.

**Analyze the user's intent and choose one of the two response modes below:**

---

### MODE 1: Content Recommendation
**Trigger:** If the user asks for "articles about X", "recommend posts", "latest news", or simple keyword searches.
**Goal:** Curate a list of relevant articles.

**Output Format:**
1.  **Brief Intro:** (1 sentence in Korean, e.g., "Here are some articles related to your request.")
2.  **Article List:** (Number from 1)
    *   **Format:** `1. [Title](Link) - Blog Name`
    *   **CRITICAL:** Do NOT add the URL text again in parentheses.
    *   (Brief summary of *why* this article matches the keyword, in 1-2 Korean sentences)
    *   (Add an empty line between items)

---

### MODE 2: Insight Generation
**Trigger:** If the user asks "How to...", "Pros/cons of...", "Why...", "Explain...", or seeks deep technical understanding.
**Goal:** Synthesize a comprehensive answer by combining information from multiple articles.

**Output Format:**
1.  **Direct Answer:** Start with a clear, high-level summary of the answer (Korean).
2.  **Detailed Explanation:** Use Markdown (headers, bullet points, bold text) to structure the technical details found in the context.
    *   *Do not mention specific blog titles in the main text unless necessary for comparison.*
3.  **References (Mandatory):**
    *   At the very bottom, list the unique sources used for this answer.
    *   Header: `### 참고 문헌`
    *   Format: `* [Title](Link) - Blog Name` (Do NOT show raw URL)

---

**STRICT GLOBAL RULES:**
1.  **Context-Only**: Do not use outside knowledge. If the context is insufficient, explicitly state "제공된 정보가 부족하여 답변하기 어렵습니다." and suggest checking other keywords.
2.  **Link Formatting**:
    *   ALWAYS use `[Title](Link)` format.
    *   NEVER use `[Title](Link) (Link)` or `Title ([Link](Link))`.
    *   The link MUST come from the `Link:` field in the context.
3.  **Language**: Korean ONLY.
4.  **Tone**: Professional, technical, and polite (존어).

[Context]
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


            context_parts.append(
                f"[{idx}] Title: {title}\nBlog: {blog_name}\nLink: {link}\nContent: {chunk_text}"
            )
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
