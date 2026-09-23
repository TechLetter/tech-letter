"""link_key와 미래 published_at 백필 CLI의 실제 Mongo 동작."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from techletter.content.links import normalize_link

pytestmark = pytest.mark.integration

ROOT = Path(__file__).parents[2]


async def run_cli(*args: str) -> str:
    env = os.environ.copy()
    # 픽스처(mongo_db)와 CLI 서브프로세스가 같은 테스트 Mongo 를 봐야 한다. 포트 하드코딩 금지.
    env["MONGO_URI"] = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27018")
    env["MONGO_DB_NAME"] = "techletter_itest"
    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "techletter",
        *args,
        cwd=ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    return stdout.decode()


async def test_link_key_backfill_dry_run_and_execute(mongo_db) -> None:
    now = datetime.now(UTC)
    collision_one: dict[str, Any] = {
        "title": "collision one",
        "link": "https://example.test/article?utm_source=a",
    }
    collision_two: dict[str, Any] = {
        "title": "collision two",
        "link": "https://example.test/article?utm_source=b",
    }
    safe: dict[str, Any] = {"title": "safe", "link": "https://example.test/other/"}
    for doc in (collision_one, collision_two, safe):
        doc.update({"created_at": now, "updated_at": now})
    inserted = await mongo_db["posts"].insert_many([collision_one, collision_two, safe])

    dry_output = await run_cli("backfill", "link-keys", "--dry-run", "--batch-size", "1")

    assert "3건" in dry_output
    assert "충돌 1쌍" in dry_output
    assert str(inserted.inserted_ids[0]) in dry_output
    assert str(inserted.inserted_ids[1]) in dry_output
    assert await mongo_db["posts"].count_documents({"link_key": {"$exists": True}}) == 0

    execute_output = await run_cli("backfill", "link-keys", "--execute", "--batch-size", "1")

    assert "1건 갱신" in execute_output
    safe_doc = await mongo_db["posts"].find_one({"_id": inserted.inserted_ids[2]})
    assert safe_doc is not None
    assert safe_doc["link_key"] == normalize_link(safe["link"])
    for post_id in inserted.inserted_ids[:2]:
        collision_doc = await mongo_db["posts"].find_one({"_id": post_id})
        assert collision_doc is not None
        assert "link_key" not in collision_doc
