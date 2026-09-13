"""포스트 link_key 인덱스와 저장소 중복 방어선."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from techletter.content.models import Post
from techletter.content.repositories import PostRepository

pytestmark = pytest.mark.integration


async def test_link_key_index_is_unique_and_partial(mongo_db) -> None:
    indexes = {idx["name"]: idx async for idx in await mongo_db["posts"].list_indexes()}

    index = indexes["uniq_link_key"]
    assert index["unique"] is True
    assert index["partialFilterExpression"] == {"link_key": {"$type": "string"}}

    now = datetime.now(UTC)
    await mongo_db["posts"].insert_many(
        [
            {"title": "legacy one", "link": "https://legacy.test/one", "created_at": now},
            {"title": "legacy two", "link": "https://legacy.test/two", "created_at": now},
        ]
    )

    assert await mongo_db["posts"].count_documents({"link_key": {"$exists": False}}) == 2


async def test_duplicate_link_key_is_absorbed_by_repository(mongo_db) -> None:
    posts = PostRepository(mongo_db)
    first = await posts.insert(Post(title="one", link="https://example.test/article"))
    assert first is not None
    assert first.link_key == "https://example.test/article"

    second = await posts.insert(
        Post(title="duplicate", link="https://example.test/article?utm_source=rss")
    )

    assert second is None
