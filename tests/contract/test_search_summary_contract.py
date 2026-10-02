"""검색 결과 AI 요약 계약 — 크레딧 없이, 같은 요청은 7일 캐시."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.contract]


class Unused:
    async def for_query(self, *args, **kwargs):
        raise AssertionError("검색하면 안 된다")

    async def for_posts(self, *args, **kwargs):
        raise AssertionError("검색하면 안 된다")


class Answers:
    def __init__(self, answer: str = "고른 글 요약 [1]") -> None:
        self.answer = answer
        self.contexts: list[str] = []

    async def brief(self, query, result):
        self.contexts.append(result.context)
        return self.answer, "test-model"


@pytest.fixture
def answers(ctx) -> Answers:
    """실제 에이전트에 LLM 대역만 끼운다. 계획·검색은 부르면 실패한다."""
    from techletter.chat.agent import ChatAgent, PostLookupTool
    from techletter.search.summary import SearchSummaryService

    fake = Answers()
    agent = ChatAgent(
        evidence=Unused(),  # type: ignore[arg-type]
        posts=PostLookupTool(ctx.posts),
        answers=fake,  # type: ignore[arg-type]
    )
    ctx._search_summary = SearchSummaryService(ctx.db, agent, ctx.sessions)
    return fake


def body(seeded, *indexes: int, query: str = "Kafka 운영") -> dict:
    return {"query": query, "post_ids": [str(seeded["posts"][i].id) for i in indexes]}


async def test_a_summary_costs_no_credit(client, ctx, user_headers, seeded, answers) -> None:
    response = await client.post(
        "/api/v1/search/summary", json=body(seeded, 2, 0), headers=user_headers
    )

    data = response.json()
    assert response.status_code == 200
    assert data["answer"] == "고른 글 요약 [1]"
    assert data["cached"] is False
    assert [s["post_id"] for s in data["sources"]] == [
        str(seeded["posts"][2].id),
        str(seeded["posts"][0].id),
    ]
    assert await ctx.credits.remaining("google:alice") == 0
    # 요약본만 읽는다.
    assert "요약 2" in answers.contexts[0]
    assert "본문 2" not in answers.contexts[0]
    # 요약을 볼 때는 세션을 만들지 않는다.
    sessions = (await client.get("/api/v1/chat/sessions", headers=user_headers)).json()
    assert sessions["total"] == 0


async def test_the_same_request_is_served_from_the_cache(
    client, user_headers, seeded, answers
) -> None:
    first = await client.post("/api/v1/search/summary", json=body(seeded, 1), headers=user_headers)
    # 검색어의 대소문자·공백은 무시한다.
    again = await client.post(
        "/api/v1/search/summary",
        json=body(seeded, 1, query="  kafka   운영 "),
        headers=user_headers,
    )

    assert again.json()["cached"] is True
    assert again.json()["key"] == first.json()["key"]
    assert len(answers.contexts) == 1


async def test_different_posts_make_a_new_summary(client, user_headers, seeded, answers) -> None:
    await client.post("/api/v1/search/summary", json=body(seeded, 1), headers=user_headers)
    await client.post("/api/v1/search/summary", json=body(seeded, 2), headers=user_headers)

    assert len(answers.contexts) == 2


async def test_continuing_opens_a_chat_session_with_the_summary(
    client, user_headers, seeded, answers
) -> None:
    key = (
        await client.post("/api/v1/search/summary", json=body(seeded, 1), headers=user_headers)
    ).json()["key"]

    response = await client.post(
        "/api/v1/search/summary/continue", json={"key": key}, headers=user_headers
    )

    session_id = response.json()["session_id"]
    session = (await client.get(f"/api/v1/chat/sessions/{session_id}", headers=user_headers)).json()
    assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
    assert session["messages"][0]["content"] == "Kafka 운영"
    assert session["messages"][1]["content"] == "고른 글 요약 [1]"
    assert len(session["messages"][1]["sources"]) == 1


async def test_continuing_an_unknown_summary_is_404(client, user_headers, answers) -> None:
    response = await client.post(
        "/api/v1/search/summary/continue", json={"key": "nope"}, headers=user_headers
    )

    assert response.status_code == 404


async def test_a_summary_needs_login(client, seeded, answers) -> None:
    response = await client.post("/api/v1/search/summary", json=body(seeded, 1))

    assert response.status_code == 401


@pytest.mark.parametrize(
    "post_ids",
    [[], ["not-an-id"], [f"{index:024x}" for index in range(9)]],
    ids=["empty", "bad-id", "too-many"],
)
async def test_bad_post_ids_are_a_typed_400(client, user_headers, answers, post_ids) -> None:
    response = await client.post(
        "/api/v1/search/summary",
        json={"query": "Kafka", "post_ids": post_ids},
        headers=user_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "request.invalid"


async def test_too_many_new_summaries_are_429(client, ctx, user_headers, seeded) -> None:
    """캐시에 없는 요청만 센다. 무료 모델 한도를 워커와 함께 쓴다."""
    from techletter.chat.agent import ChatAgent, PostLookupTool
    from techletter.search.summary import SearchSummaryService

    agent = ChatAgent(
        evidence=Unused(),  # type: ignore[arg-type]
        posts=PostLookupTool(ctx.posts),
        answers=Answers(),  # type: ignore[arg-type]
    )
    ctx._search_summary = SearchSummaryService(ctx.db, agent, ctx.sessions, misses_per_minute=1)

    ok = await client.post("/api/v1/search/summary", json=body(seeded, 1), headers=user_headers)
    cached = await client.post("/api/v1/search/summary", json=body(seeded, 1), headers=user_headers)
    limited = await client.post(
        "/api/v1/search/summary", json=body(seeded, 2), headers=user_headers
    )

    assert (ok.status_code, cached.status_code, limited.status_code) == (200, 200, 429)
