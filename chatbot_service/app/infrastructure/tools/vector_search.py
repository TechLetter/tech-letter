from __future__ import annotations

from common.llm.utils import normalize_model_name

from ...domain.chat.schemas import PostConstraints, Source, ToolResult
from ...services.context_builder import ContextBuilder
from ...vector_store import VectorStore


class VectorSearchAdapter:
    def __init__(
        self,
        *,
        embeddings,
        embedding_model_name: str,
        vector_store: VectorStore,
        context_builder: ContextBuilder,
        default_top_k: int,
        default_score_threshold: float,
    ) -> None:
        self._embeddings = embeddings
        self._embedding_model_key = normalize_model_name(embedding_model_name)
        self._vector_store = vector_store
        self._context_builder = context_builder
        self._default_top_k = default_top_k
        self._default_score_threshold = default_score_threshold

    def search(
        self,
        query: str,
        constraints: PostConstraints | None = None,
    ) -> ToolResult:
        query_vector = self._embeddings.embed_query(query)
        limit = constraints.limit if constraints else self._default_top_k
        search_results = self._vector_store.search(
            query_vector,
            self._embedding_model_key,
            limit=limit,
            score_threshold=self._default_score_threshold,
        )
        if not search_results:
            return ToolResult(
                status="no_result",
                context="",
                sources=[],
                total=0,
                message="관련 정보를 찾지 못했습니다.",
            )

        built_context = self._context_builder.build(search_results)
        return ToolResult(
            status="ok",
            context=built_context.context,
            sources=[
                Source(
                    title=source["title"],
                    blog_name=source["blog_name"],
                    link=source["link"],
                    score=source["score"],
                )
                for source in built_context.sources
            ],
            total=len(built_context.sources),
            message="관련 글 검색을 완료했습니다.",
        )
