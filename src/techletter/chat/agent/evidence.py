"""답변 근거 — 글을 먼저 고르고, 그 글 안에서 청크를 고른다.

글은 목록 검색과 같은 하이브리드 검색(`SearchService.retrieve`: BM25 + 벡터, RRF,
최신성)이 고른다. 예전 챗봇은 벡터 청크만 봐서 이름이 정확히 나오는 글도 놓쳤다.

근거 번호는 **글 단위**다. 같은 글의 청크는 같은 `[n]`을 쓰고 `sources[n-1]`이 그 글이다.
프롬프트에 넣지 않은 글은 출처에도 넣지 않는다.

벡터 색인이 아직 없는 글(임베딩 대기)이나 질의 임베딩이 막혔을 때는 저장된 요약과
본문 앞부분을 근거로 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.chat.agent.state import PostRecord, Source, ToolResult
from techletter.chat.agent.tools.content_posts import post_record
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import ListPostsFilter, Post
    from techletter.content.repositories import PostRepository
    from techletter.core.db.qdrant import SearchHit, VectorStore
    from techletter.search.service import SearchService

__all__ = ["Evidence", "EvidenceBuilder"]

logger = get_logger(__name__)

# 이름만 나온 블로그의 글을 앞으로 올릴 때 볼 후보 수.
_BOOST_WINDOW = 20


@dataclass(slots=True)
class Evidence:
    records: list[PostRecord]
    context: str
    sources: list[Source]


class EvidenceBuilder:
    def __init__(
        self,
        *,
        search: SearchService,
        store: VectorStore,
        posts: PostRepository,
        embedding_model: str,
        max_posts: int = 5,
        chunks_per_post: int = 2,
        max_chunk_chars: int = 1500,
        fallback_body_chars: int = 2000,
    ) -> None:
        self._search = search
        self._store = store
        self._posts = posts
        self._embedding_model = embedding_model
        self._max_posts = max_posts
        self._chunks_per_post = chunks_per_post
        self._max_chunk_chars = max_chunk_chars
        self._fallback_body_chars = fallback_body_chars

    async def rank(
        self,
        query: str,
        flt: ListPostsFilter,
        *,
        client: str | None = None,
        boost_blog_id: str | None = None,
        limit: int | None = None,
        exclude_ids: frozenset[str] = frozenset(),
        exclude_blog_ids: frozenset[str] = frozenset(),
    ) -> tuple[list[Post], list[float] | None]:
        """관련도 순 글(요약된 글만)과 질의 벡터."""
        retrieval = await self._search.retrieve(query, flt, client=client)
        limit = limit or self._max_posts
        ranked = [pid for pid in retrieval.post_ids if pid not in exclude_ids]
        wide = boost_blog_id or exclude_blog_ids
        window = ranked[: max(limit, _BOOST_WINDOW) if wide else limit]
        found = await self._posts.get_many(window)
        ordered = [
            found[pid]
            for pid in window
            if pid in found and str(found[pid].blog_id) not in exclude_blog_ids
        ]
        if boost_blog_id:
            # 이름만 나온 블로그는 좁히지 않고 그 블로그 글을 앞으로 올린다(안정 정렬).
            ordered.sort(key=lambda post: str(post.blog_id) != boost_blog_id)
        return ordered[:limit], retrieval.vector

    async def for_query(
        self,
        query: str,
        flt: ListPostsFilter,
        *,
        client: str | None = None,
        boost_blog_id: str | None = None,
        exclude_ids: frozenset[str] = frozenset(),
        exclude_blog_ids: frozenset[str] = frozenset(),
    ) -> ToolResult:
        posts, vector = await self.rank(
            query,
            flt,
            client=client,
            boost_blog_id=boost_blog_id,
            exclude_ids=exclude_ids,
            exclude_blog_ids=exclude_blog_ids,
        )
        return await self._build(posts, vector)

    async def for_posts(
        self, query: str, post_ids: list[str], *, client: str | None = None
    ) -> ToolResult:
        """정해진 글(직전 답의 출처) 안에서 질문에 맞는 부분을 고른다."""
        found = await self._posts.get_many(post_ids)
        posts = [
            found[pid] for pid in post_ids if pid in found and found[pid].status.ai_summarized
        ][: self._max_posts]
        vector = await self._search.embed(query, client) if posts else None
        return await self._build(posts, vector)

    async def _build(self, posts: list[Post], vector: list[float] | None) -> ToolResult:
        if not posts:
            return ToolResult(status="no_result", message="관련 글을 찾지 못했습니다.")
        ids = [str(post.id) for post in posts]
        chunks: dict[str, list[SearchHit]] = {}
        if vector is not None:
            try:
                chunks = await self._store.search_in_posts(
                    vector, self._embedding_model, ids, per_post=self._chunks_per_post
                )
            except Exception:
                # 청크를 못 읽어도 요약·본문 앞부분으로 답한다.
                logger.warning("chunk search failed; using summaries", exc_info=True)
        missing = [pid for pid in ids if not chunks.get(pid)]
        bodies = await self._posts.get_plain_texts(missing) if missing else {}

        records = [post_record(post) for post in posts]
        blocks: list[str] = []
        sources: list[Source] = []
        for index, record in enumerate(records, 1):
            hits = chunks.get(record.id) or []
            if hits:
                # 글 안의 순서대로 놓아야 읽힌다.
                hits = sorted(hits, key=lambda hit: int(hit.payload.get("chunk_index") or 0))
                body = "\n…\n".join(
                    str(hit.payload.get("chunk_text") or "")[: self._max_chunk_chars]
                    for hit in hits
                )
            else:
                body = (bodies.get(record.id) or "")[: self._fallback_body_chars]
            published = record.published_at[:10] if record.published_at else ""
            blocks.append(
                "\n".join(
                    part
                    for part in (
                        f"[{index}] {record.title} — {record.blog_name} ({published})",
                        f"요약: {record.summary}" if record.summary else "",
                        f"본문 발췌:\n{body}" if body else "",
                    )
                    if part
                )
            )
            best = max((hit.score for hit in hits), default=1.0)
            sources.append(
                Source(
                    post_id=record.id,
                    title=record.title,
                    blog_name=record.blog_name,
                    link=record.link,
                    score=round(best, 4),
                    blog_id=record.blog_id,
                    published_at=record.published_at or None,
                )
            )
        return ToolResult(
            status="ok",
            posts=records,
            context="\n\n".join(blocks),
            sources=sources,
            total=len(records),
        )
