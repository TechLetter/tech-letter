"""글 "쉽게 읽기" 계약 — 요약 완료 잡이 저장하고, 공개 API가 noindex로 준다."""

from __future__ import annotations

import pytest

from techletter.content.handlers import SummaryCompletedHandler
from techletter.content.jobs import SummaryCompletedPayload
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.explainer.models import Explainer, Tldr

pytestmark = [pytest.mark.integration, pytest.mark.contract]


def explainer_for(post_id: str) -> dict:
    return Explainer(
        post_id=post_id,  # type: ignore[arg-type]
        post_type="case",
        difficulty="beginner",
        reading_minutes=4,
        tldr=Tldr(one_liner="한 문장 요약입니다.", points=["하나", "둘", "셋"]),
        body_md="## 배경\n본문입니다.",
        categories=["메시징·스트리밍"],
        tags=["Kafka"],
    ).model_dump(mode="json", by_alias=True, exclude={"id"})


async def test_a_completed_summary_stores_the_explainer(client, ctx, seeded) -> None:
    post = seeded["posts"][0]
    pid = str(post.id)
    payload = SummaryCompletedPayload(
        post_id=pid,
        summary="한 문장 요약입니다.",
        categories=["메시징·스트리밍"],
        tags=["Kafka"],
        model_name="gemini-3-flash-preview",
        explainer=explainer_for(pid),
    )

    await SummaryCompletedHandler(ctx.posts, ctx.queue, ctx.explainers)(
        Job(type=JobType.SUMMARY_COMPLETED, key=pid, payload=payload.to_dict())
    )

    response = await client.get(f"/api/v1/posts/{pid}/explainer")
    body = response.json()
    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert body["one_liner"] == "한 문장 요약입니다."
    assert body["points"] == ["하나", "둘", "셋"]
    assert body["body_md"].startswith("## 배경")
    # 카드·검색·챗봇이 쓰는 기존 요약 자리에도 같은 한 문장이 들어간다.
    card = (await client.get(f"/api/v1/posts/{pid}")).json()
    assert card["summary"] == "한 문장 요약입니다."


async def test_a_post_without_an_explainer_is_404(client, seeded) -> None:
    response = await client.get(f"/api/v1/posts/{seeded['posts'][1].id}/explainer")

    assert response.status_code == 404


async def test_an_unknown_post_is_404(client) -> None:
    response = await client.get("/api/v1/posts/6a0000000000000000000099/explainer")

    assert response.status_code == 404


async def test_deleting_a_post_removes_its_explainer(ctx, seeded) -> None:
    post = seeded["posts"][2]
    await ctx.explainers.upsert(Explainer.model_validate(explainer_for(str(post.id))))

    await ctx.posts.delete(str(post.id))

    assert await ctx.explainers.get(str(post.id)) is None
