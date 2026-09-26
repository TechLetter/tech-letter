"""포스트 검색 — 어휘(BM25)와 벡터를 RRF로 섞는다.

어휘 검색은 "vllm", "카프카"처럼 단어가 그대로 들어간 글을 잘 찾고, 벡터 검색은
표현이 달라도 뜻이 가까운 글을 찾는다. 점수 척도가 서로 달라 더하지 않고 순위로
섞는다(RRF). 벡터로만 걸린 글은 점수가 충분히 높을 때만 남긴다 — 벡터 검색은
무엇을 물어도 무언가를 돌려주기 때문이다.

자동완성은 어휘 검색만 쓴다. 글자를 칠 때마다 임베딩을 부르면 분당 한도를 금방 넘는다.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from techletter.content.models import ListPostsFilter
from techletter.core.logging import get_logger
from techletter.core.time import ensure_utc, utcnow
from techletter.search.lexical import query_vector

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from datetime import datetime

    from techletter.content.models import Post
    from techletter.content.repositories import PostRepository
    from techletter.core.db.qdrant import SearchHit, VectorStore
    from techletter.core.pagination import Page
    from techletter.settings import SearchSettings

__all__ = [
    "MAX_QUERY_CHARS",
    "MIN_QUERY_CHARS",
    "EmbedRateLimiter",
    "QueryVectorCache",
    "SearchService",
    "Suggestion",
    "group_dense",
    "normalize_query",
    "recency_factor",
    "rrf_fuse",
]

logger = get_logger(__name__)

MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 100


def normalize_query(raw: str | None) -> str | None:
    """공백을 정리한다. 두 글자 미만이면 검색하지 않고(None), 100자에서 자른다."""
    text = " ".join((raw or "").split())
    if len(text) < MIN_QUERY_CHARS:
        return None
    return text[:MAX_QUERY_CHARS].strip()


def rrf_fuse(rankings: list[list[str]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion: Σ 1/(k + 순위). 순위는 1부터다.

    반환 dict는 처음 나온 순서를 유지한다 — 동점이면 앞 목록(어휘)의 순서를 따른다.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def recency_factor(
    published_at: datetime | None,
    now: datetime,
    *,
    half_life_days: float,
    min_factor: float,
) -> float:
    """0.5^(경과일/반감기), 하한 `min_factor`. 발행일이 없으면 하한을 준다."""
    if published_at is None:
        return min_factor
    if half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (now - ensure_utc(published_at)).total_seconds() / 86400)
    return max(min_factor, 0.5 ** (age_days / half_life_days))


def group_dense(hits: list[SearchHit]) -> list[tuple[str, float]]:
    """청크 결과를 포스트별 최고 점수로 묶어 점수순으로 준다."""
    best: dict[str, float] = {}
    for hit in hits:
        post_id = str(hit.payload.get("post_id") or "")
        if post_id and hit.score > best.get(post_id, float("-inf")):
            best[post_id] = hit.score
    return sorted(best.items(), key=lambda item: item[1], reverse=True)


class QueryEmbedder(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


class QueryVectorCache:
    """질의 벡터 LRU. 같은 검색어로 페이지를 넘길 때 임베딩을 다시 부르지 않는다."""

    def __init__(
        self, max_size: int, ttl_seconds: float, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()

    def get(self, key: str) -> list[float] | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry[0] <= self._clock():
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return entry[1]

    def put(self, key: str, vector: list[float]) -> None:
        if self._max_size <= 0:
            return
        self._items[key] = (self._clock() + self._ttl, vector)
        self._items.move_to_end(key)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)


class EmbedRateLimiter:
    """클라이언트별 분당 질의 임베딩 횟수 제한.

    검색 임베딩은 챗봇·임베딩 워커와 같은 Gemini 분당 한도를 쓴다. 누가 검색을
    두드려도 그 한도가 바닥나지 않게, 넘치면 벡터 검색만 건너뛴다(어휘 결과는 준다).
    API 프로세스 하나의 메모리에만 있다 — 프로세스가 늘면 한도도 그만큼 늘어난다.
    """

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, client: str | None) -> bool:
        if self._per_minute <= 0 or not client:
            return True
        now = self._clock()
        window = self._hits.setdefault(client, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= self._per_minute:
            return False
        window.append(now)
        if len(self._hits) > 10_000:  # 오래 조용한 클라이언트를 한 번씩 비운다
            self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - 60}
        return True


@dataclass(frozen=True, slots=True)
class Suggestion:
    post_id: str
    title: str
    blog_id: str | None
    blog_name: str
    published_at: str | None
    link: str


class SearchService:
    def __init__(
        self,
        *,
        store: VectorStore,
        posts: PostRepository,
        embedder: QueryEmbedder,
        embedding_model: str,
        settings: SearchSettings,
        cache: QueryVectorCache | None = None,
        limiter: EmbedRateLimiter | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._posts = posts
        self._embedder = embedder
        self._embedding_model = embedding_model
        self._settings = settings
        self._cache = cache or QueryVectorCache(
            settings.query_cache_size, settings.query_cache_ttl_seconds
        )
        self._limiter = limiter or EmbedRateLimiter(settings.embeds_per_minute_per_client)
        self._now = now

    async def suggest(self, raw: str | None) -> list[Suggestion]:
        query = normalize_query(raw)
        if query is None:
            return []
        try:
            hits = await self._store.search_lexical(
                query_vector(query).indices, limit=self._settings.suggest_limit
            )
        except Exception:
            logger.warning("lexical suggest failed", exc_info=True)
            return []
        # 표시 값은 payload에서 바로 쓰고, 지금도 공개 대상인지만 Mongo에 묻는다.
        # 삭제 잡이 밀려 있거나 요약이 되돌려진 글이 자동완성에 남지 않게.
        visible = await self._posts.matching_ids(
            ListPostsFilter(summarized=True),
            [str(hit.payload.get("post_id") or "") for hit in hits],
        )
        return [
            Suggestion(
                post_id=str(hit.payload.get("post_id") or ""),
                title=str(hit.payload.get("title") or ""),
                blog_id=hit.payload.get("blog_id") or None,
                blog_name=str(hit.payload.get("blog_name") or ""),
                published_at=hit.payload.get("published_at") or None,
                link=str(hit.payload.get("link") or ""),
            )
            for hit in hits
            if str(hit.payload.get("post_id") or "") in visible
        ]

    async def search(
        self, query: str, flt: ListPostsFilter, page: Page, *, client: str | None = None
    ) -> tuple[list[Post], int]:
        """관련도 순 한 페이지와 전체 건수. `query`는 `normalize_query`를 거친 값이다.

        `client`는 요청자 IP. 질의 임베딩 횟수 제한(`EmbedRateLimiter`)에 쓴다.
        """
        ranked = await self.rank(query, flt, client=client)
        page_ids = ranked[page.skip : page.skip + page.page_size]
        found = await self._posts.get_many(page_ids)
        return [found[post_id] for post_id in page_ids if post_id in found], len(ranked)

    async def rank(
        self, query: str, flt: ListPostsFilter, *, client: str | None = None
    ) -> list[str]:
        """필터를 통과한 포스트 id를 관련도 순으로 준다(최대 `max_results`)."""
        lexical = await self._lexical(query, flt)
        lexical_ids = [str(hit.payload.get("post_id") or "") for hit in lexical]
        lexical_ids = [post_id for post_id in lexical_ids if post_id]
        in_lexical = set(lexical_ids)

        dense = await self._dense(query, client)
        dense_ids = [
            post_id
            for post_id, score in dense
            if post_id in in_lexical or score >= self._settings.dense_min_score
        ]

        fused = rrf_fuse([lexical_ids, dense_ids], self._settings.rrf_k)
        if not fused:
            return []
        # 필터·요약 여부는 Mongo가 판정한다. 벡터 쪽 payload에는 주제·블로그 id가 없다.
        published = await self._posts.matching_ids(flt, list(fused))
        now = self._now()
        order = {post_id: index for index, post_id in enumerate(fused)}
        scored = [
            (
                fused[post_id]
                * recency_factor(
                    published_at,
                    now,
                    half_life_days=self._settings.recency_half_life_days,
                    min_factor=self._settings.recency_min_factor,
                ),
                post_id,
            )
            for post_id, published_at in published.items()
        ]
        scored.sort(key=lambda item: (-item[0], order[item[1]]))
        return [post_id for _, post_id in scored[: self._settings.max_results]]

    async def _lexical(self, query: str, flt: ListPostsFilter) -> list[SearchHit]:
        # 주제와 태그가 함께 오면 목록 API는 합집합으로 거른다. 주제만으로 미리
        # 좁히면 태그로만 맞는 글이 빠지므로, 그때는 Mongo 필터에 맡긴다.
        categories = flt.categories if flt.categories and not flt.tags else None
        try:
            return await self._store.search_lexical(
                query_vector(query).indices,
                limit=self._settings.lexical_candidates,
                blog_id=flt.blog_id,
                categories=categories,
            )
        except Exception:
            logger.warning("lexical search failed; using dense only", exc_info=True)
            return []

    async def _dense(self, query: str, client: str | None = None) -> list[tuple[str, float]]:
        try:
            vector = self._cache.get(query)
            if vector is None:
                # 캐시에 있는 검색어는 임베딩을 안 부르니 세지 않는다.
                if not self._limiter.allow(client):
                    logger.info("query embedding rate limited; using lexical only")
                    return []
                vector = await self._embedder.embed_query(query)
                self._cache.put(query, vector)
            hits = await self._store.search(
                vector,
                self._embedding_model,
                limit=self._settings.dense_candidates,
                score_threshold=0.0,
            )
        except Exception:
            # 임베딩 한도·Qdrant 장애가 검색 전체를 막지 않게 어휘 결과만으로 답한다.
            logger.warning("dense search failed; using lexical only", exc_info=True)
            return []
        return group_dense(hits)
