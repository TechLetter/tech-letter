"""검색 순위 — 질의 정규화, RRF, 최신성 감쇠, 벡터 장애 대체."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from techletter.content.models import ListPostsFilter
from techletter.core.db.qdrant import SearchHit
from techletter.core.errors import VectorStoreUnavailableError
from techletter.search.service import (
    EmbedRateLimiter,
    QueryVectorCache,
    SearchService,
    group_dense,
    normalize_query,
    recency_factor,
    rrf_fuse,
)
from techletter.settings import SearchSettings

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


# ── 질의 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw", [None, "", " ", "a", " 카 "])
def test_too_short_queries_mean_no_search(raw) -> None:
    assert normalize_query(raw) is None


def test_queries_are_trimmed_and_collapsed() -> None:
    assert normalize_query("  vllm   서빙 ") == "vllm 서빙"


def test_long_queries_are_cut_at_100_chars() -> None:
    query = normalize_query("가" * 150)

    assert query is not None
    assert len(query) == 100


# ── RRF ─────────────────────────────────────────────────────────────
def test_rrf_rewards_items_found_by_both() -> None:
    scores = rrf_fuse([["a", "b"], ["b", "c"]], k=60)

    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["a"] == pytest.approx(1 / 61)
    assert max(scores, key=lambda key: scores[key]) == "b"


def test_rrf_keeps_first_seen_order() -> None:
    assert list(rrf_fuse([["a", "b"], ["c"]], k=60)) == ["a", "b", "c"]


def test_dense_hits_are_grouped_by_post_with_the_best_score() -> None:
    hits = [
        SearchHit(score=0.6, payload={"post_id": "p1"}),
        SearchHit(score=0.9, payload={"post_id": "p2"}),
        SearchHit(score=0.8, payload={"post_id": "p1"}),
        SearchHit(score=0.99, payload={}),
    ]

    assert group_dense(hits) == [("p2", 0.9), ("p1", 0.8)]


# ── 최신성 ──────────────────────────────────────────────────────────
def factor(age_days: float) -> float:
    return recency_factor(days_ago(age_days), NOW, half_life_days=1100, min_factor=0.5)


def test_recency_decays_mildly() -> None:
    assert factor(0) == pytest.approx(1.0)
    assert factor(365) == pytest.approx(0.8, abs=0.01)
    assert factor(730) == pytest.approx(0.63, abs=0.02)


def test_recency_has_a_floor() -> None:
    assert factor(365 * 20) == 0.5


def test_future_dates_are_not_boosted() -> None:
    assert factor(-30) == 1.0


def test_a_missing_date_gets_the_floor() -> None:
    assert recency_factor(None, NOW, half_life_days=1100, min_factor=0.5) == 0.5


# ── 서비스 ──────────────────────────────────────────────────────────
class FakeStore:
    def __init__(
        self,
        lexical: list[str],
        dense: list[tuple[str, float]] | None = None,
        *,
        dense_error: Exception | None = None,
    ) -> None:
        self.lexical = lexical
        self.dense = dense or []
        self.dense_error = dense_error
        self.lexical_calls: list[dict] = []

    async def search_lexical(self, indices, *, limit, blog_id=None, categories=None):
        self.lexical_calls.append({"blog_id": blog_id, "categories": categories})
        return [SearchHit(score=1.0, payload={"post_id": post_id}) for post_id in self.lexical]

    async def search(self, vector, model_name, *, limit, score_threshold):
        if self.dense_error is not None:
            raise self.dense_error
        return [SearchHit(score=score, payload={"post_id": pid}) for pid, score in self.dense]


class FakePosts:
    def __init__(self, published: dict[str, datetime | None]) -> None:
        self.published = published

    async def matching_ids(self, flt, post_ids):
        return {pid: self.published[pid] for pid in post_ids if pid in self.published}


class FakeEmbedder:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def embed_query(self, text: str) -> list[float]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return [0.1, 0.2]


def service(store, posts, embedder=None, **settings) -> SearchService:
    return SearchService(
        store=store,  # type: ignore[arg-type]
        posts=posts,  # type: ignore[arg-type]
        embedder=embedder or FakeEmbedder(),
        embedding_model="fake",
        settings=SearchSettings(**settings),
        now=lambda: NOW,
    )


async def test_an_equally_relevant_newer_post_ranks_first() -> None:
    """같은 순위로 걸렸으면 최신 글이 위다."""
    store = FakeStore(lexical=["old", "new"], dense=[("new", 0.9), ("old", 0.9)])
    posts = FakePosts({"old": days_ago(800), "new": days_ago(10)})

    assert await service(store, posts).rank("kafka", ListPostsFilter()) == ["new", "old"]


async def test_a_much_more_relevant_old_post_still_wins() -> None:
    """양쪽에서 1위인 오래된 글이 한쪽 끝에 겨우 걸린 새 글보다 위다."""
    filler = [f"f{i}" for i in range(30)]
    store = FakeStore(lexical=["old", *filler, "new"], dense=[("old", 0.95)])
    published: dict[str, datetime | None] = {"old": days_ago(365 * 6), "new": days_ago(1)}
    published.update(dict.fromkeys(filler, days_ago(100)))

    ranked = await service(store, FakePosts(published)).rank("kafka", ListPostsFilter())

    assert ranked.index("old") < ranked.index("new")


async def test_dense_only_hits_need_a_high_score() -> None:
    store = FakeStore(lexical=["lex"], dense=[("strong", 0.8), ("weak", 0.6), ("lex", 0.1)])
    posts = FakePosts(dict.fromkeys(["lex", "strong", "weak"], NOW))

    ranked = await service(store, posts, dense_min_score=0.7).rank("q1", ListPostsFilter())

    assert set(ranked) == {"lex", "strong"}
    assert ranked[0] == "lex"  # 양쪽에서 걸렸다


async def test_posts_filtered_out_by_mongo_are_dropped() -> None:
    store = FakeStore(lexical=["a", "b"])

    ranked = await service(store, FakePosts({"b": NOW})).rank("q1", ListPostsFilter())

    assert ranked == ["b"]


async def test_results_are_capped() -> None:
    ids = [f"p{i}" for i in range(10)]
    store = FakeStore(lexical=ids)

    ranked = await service(store, FakePosts(dict.fromkeys(ids, NOW)), max_results=3).rank(
        "q1", ListPostsFilter()
    )

    assert ranked == ["p0", "p1", "p2"]


@pytest.mark.parametrize(
    ("embed_error", "dense_error"),
    [(RuntimeError("quota"), None), (None, VectorStoreUnavailableError("down"))],
)
async def test_dense_failure_falls_back_to_lexical(embed_error, dense_error) -> None:
    store = FakeStore(lexical=["a"], dense=[("b", 0.99)], dense_error=dense_error)
    embedder = FakeEmbedder(embed_error)

    ranked = await service(store, FakePosts({"a": NOW, "b": NOW}), embedder).rank(
        "q1", ListPostsFilter()
    )

    assert ranked == ["a"]


async def test_query_vectors_are_cached() -> None:
    embedder = FakeEmbedder()
    search = service(FakeStore(lexical=["a"]), FakePosts({"a": NOW}), embedder)

    await search.rank("kafka", ListPostsFilter())
    await search.rank("kafka", ListPostsFilter())

    assert embedder.calls == 1


async def test_categories_prefilter_lexical_only_without_tags() -> None:
    """주제+태그는 합집합이라 주제로 미리 좁히면 태그로 맞는 글이 빠진다."""
    store = FakeStore(lexical=[])
    search = service(store, FakePosts({}))

    await search.rank("q1", ListPostsFilter(categories=["데이터"], blog_id="b1"))
    await search.rank("q1", ListPostsFilter(categories=["데이터"], tags=["Kafka"]))

    assert store.lexical_calls == [
        {"blog_id": "b1", "categories": ["데이터"]},
        {"blog_id": None, "categories": None},
    ]


async def test_suggest_skips_short_queries_and_never_embeds() -> None:
    embedder = FakeEmbedder()
    store = FakeStore(lexical=["a", "gone"])
    search = service(store, FakePosts({"a": NOW}), embedder)

    assert await search.suggest("k") == []
    items = await search.suggest("kafka")

    assert [item.post_id for item in items] == ["a"]  # Mongo에 없는 글은 뺀다
    assert embedder.calls == 0


# ── 캐시 ────────────────────────────────────────────────────────────
def test_cache_expires_entries() -> None:
    now = [0.0]
    cache = QueryVectorCache(10, 60, clock=lambda: now[0])
    cache.put("q", [1.0])

    assert cache.get("q") == [1.0]
    now[0] = 61
    assert cache.get("q") is None


def test_cache_evicts_the_least_recently_used() -> None:
    cache = QueryVectorCache(2, 60, clock=lambda: 0.0)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    cache.get("a")
    cache.put("c", [3.0])

    assert cache.get("b") is None
    assert cache.get("a") == [1.0]


# ── 임베딩 횟수 제한 ────────────────────────────────────────────────
def test_the_limiter_allows_n_per_minute_per_client() -> None:
    now = [0.0]
    limiter = EmbedRateLimiter(2, clock=lambda: now[0])

    assert [limiter.allow("1.1.1.1") for _ in range(3)] == [True, True, False]
    assert limiter.allow("2.2.2.2")  # 다른 클라이언트는 따로 센다
    now[0] = 61
    assert limiter.allow("1.1.1.1")


async def test_a_limited_client_gets_lexical_results_only() -> None:
    """한도를 넘으면 임베딩을 부르지 않고 어휘 결과만 준다. 캐시된 검색어는 세지 않는다."""
    embedder = FakeEmbedder()
    store = FakeStore(lexical=["a"], dense=[("b", 0.99)])
    search = service(
        store, FakePosts({"a": NOW, "b": NOW}), embedder, embeds_per_minute_per_client=1
    )

    first = await search.rank("kafka", ListPostsFilter(), client="1.1.1.1")
    cached = await search.rank("kafka", ListPostsFilter(), client="1.1.1.1")
    limited = await search.rank("vllm", ListPostsFilter(), client="1.1.1.1")

    assert set(first) == set(cached) == {"a", "b"}
    assert limited == ["a"]
    assert embedder.calls == 1
