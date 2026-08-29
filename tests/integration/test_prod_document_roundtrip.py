"""운영 DB에서 그대로 떠 온 문서로 모델을 검증한다.

손으로 만든 픽스처는 우리가 상상한 스키마를 확인할 뿐이다. 여기서 쓰는
문서는 2026-08-29 운영 `techletter` DB에서 뽑은 실물이며(`plain_text`만
120자로 잘랐다), 공개된 기술 블로그 내용이라 개인정보가 없다.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest
from bson import json_util

from techletter.content.models import Blog, ListPostsFilter, Post
from techletter.content.repositories import BlogRepository, PostRepository
from techletter.core.pagination import Page

pytestmark = pytest.mark.integration

SAMPLE = json_util.loads(
    (Path(__file__).parents[1] / "fixtures" / "seed" / "prod_content_sample.json").read_text(
        encoding="utf-8"
    )
)
POSTS = [*SAMPLE["posts"], *SAMPLE["unsummarized"], *SAMPLE["oldest"]]
BLOGS = SAMPLE["blogs"]


@pytest.mark.parametrize("doc", POSTS, ids=lambda d: str(d["_id"]))
def test_every_production_post_validates(doc: dict) -> None:
    post = Post.model_validate(doc)

    assert post.id == doc["_id"]
    assert post.published_at is not None
    assert post.published_at.tzinfo is not None


@pytest.mark.parametrize("doc", BLOGS, ids=lambda d: d["name"])
def test_every_production_blog_validates(doc: dict) -> None:
    blog = Blog.model_validate(doc)

    assert blog.name == doc["name"]
    # 운영 blogs 문서에는 is_active 필드가 아예 없다. 기본이 활성이어야
    # 다음 수집 사이클에서 블로그가 통째로 빠지지 않는다.
    assert "is_active" not in doc
    assert blog.is_active is True
    assert blog.consecutive_failures == 0
    assert blog.tls_insecure is False


def test_summarized_post_keeps_its_summary_and_embedding_metadata() -> None:
    post = Post.model_validate(SAMPLE["posts"][0])

    assert post.status.ai_summarized is True
    assert post.aisummary is not None
    assert post.aisummary.summary
    assert post.aisummary.model_name
    assert post.embedding is not None
    assert post.embedding.vector_dimension == 3072
    assert post.embedding.chunk_count > 0


def test_unsummarized_post_carries_empty_strings_not_nulls() -> None:
    """현행 수집기가 빈 문자열로 채운다. 모델이 이를 그대로 받아야 한다."""
    doc = SAMPLE["unsummarized"][0]
    post = Post.model_validate(doc)

    assert doc["thumbnail_url"] == ""
    assert post.thumbnail_url == ""
    assert post.aisummary is not None
    assert post.aisummary.categories == []
    assert post.embedding is None


def test_a_2017_publication_date_survives() -> None:
    """가장 오래된 포스트. epoch 변환이 틀리면 여기서 드러난다."""
    post = Post.model_validate(SAMPLE["oldest"][0])

    assert post.published_at is not None
    assert post.published_at.year == 2017
    assert post.published_at.tzinfo == UTC


async def test_documents_survive_a_write_read_cycle(mongo_db) -> None:
    posts = PostRepository(mongo_db)
    for doc in POSTS:
        await mongo_db["posts"].insert_one(doc)

    for doc in POSTS:
        found = await posts.get(str(doc["_id"]))

        assert found is not None
        assert found.title == doc["title"]
        assert found.link == doc["link"]
        assert found.published_at == doc["published_at"].replace(tzinfo=UTC)
        assert found.aisummary is not None
        assert found.aisummary.tags == doc["aisummary"]["tags"]


async def test_real_documents_answer_the_real_queries(mongo_db) -> None:
    posts = PostRepository(mongo_db)
    await mongo_db["posts"].insert_many([dict(doc) for doc in POSTS])

    _, summarized = await posts.list_posts(ListPostsFilter(summarized=True), Page(1, 50))
    _, pending = await posts.list_posts(ListPostsFilter(summarized=False), Page(1, 50))
    tags = await posts.tag_counts(None, [])

    assert summarized == 3
    assert pending == 2
    assert "LLM" in tags


async def test_a_blog_without_is_active_is_still_collected(mongo_db) -> None:
    blogs = BlogRepository(mongo_db)
    await mongo_db["blogs"].insert_many([dict(doc) for doc in BLOGS])

    active = await blogs.list_active()

    assert len(active) == len(BLOGS)
