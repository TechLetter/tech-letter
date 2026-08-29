"""에이전트 그래프 — 어떤 도구를 타고 무엇을 답하는가."""

from __future__ import annotations

import asyncio

import pytest

from techletter.chat.agent.answer import (
    NO_RESULT_MESSAGE,
    AnswerGenerator,
    build_post_context,
    format_post_list,
)
from techletter.chat.agent.graph import ChatAgent
from techletter.chat.agent.state import (
    Activity,
    ChatPlan,
    PostConstraints,
    PostRecord,
    Source,
    ToolResult,
)
from techletter.chat.memory import MemoryContext


class FakePlanner:
    def __init__(self, plan: ChatPlan) -> None:
        self.plan_result = plan
        self.queries: list[str] = []

    async def plan(self, query: str, memory_metadata: dict) -> ChatPlan:
        self.queries.append(query)
        return self.plan_result


def record(index: int) -> PostRecord:
    return PostRecord(
        id=f"id{index}",
        title=f"제목{index}",
        link=f"https://blog.test/{index}",
        blog_name="Alpha",
        published_at="2025-03-01T00:00:00.000Z",
        summary=f"요약{index}",
        tags=["Kafka"],
    )


class FakePosts:
    def __init__(self, result: ToolResult | None = None) -> None:
        self.result = result or ToolResult(
            status="ok",
            posts=[record(1)],
            sources=[Source(post_id="id1", title="제목1", blog_name="Alpha", link="l")],
            total=1,
            message="조회했습니다.",
        )
        self.hydrated = False

    async def list_posts(self, constraints: PostConstraints) -> ToolResult:
        return self.result

    async def hydrate(self, records: list[PostRecord]) -> list[PostRecord]:
        self.hydrated = True
        for item in records:
            item.plain_text = f"본문 {item.id}"
        return records


class FakeSearch:
    def __init__(self, result: ToolResult | None = None) -> None:
        self.result = result or ToolResult(
            status="ok", context="검색 문맥", total=1, message="검색 완료"
        )
        self.calls: list[tuple[str, bool]] = []

    async def search(self, query: str, constraints: PostConstraints | None = None) -> ToolResult:
        self.calls.append((query, constraints is not None))
        return self.result


class FakeAnswers:
    def __init__(self, answer: str = "답변") -> None:
        self.answer = answer
        self.seen: list[ToolResult] = []

    async def generate(self, query, plan, result, memory_metadata):
        self.seen.append(result)
        return self.answer


def build(
    plan: ChatPlan,
    *,
    posts: FakePosts | None = None,
    search: FakeSearch | None = None,
    answers: FakeAnswers | None = None,
) -> tuple[ChatAgent, FakePosts, FakeSearch, FakeAnswers]:
    posts = posts or FakePosts()
    search = search or FakeSearch()
    answers = answers or FakeAnswers()
    agent = ChatAgent(
        planner=FakePlanner(plan),  # type: ignore[arg-type]
        posts=posts,  # type: ignore[arg-type]
        search=search,  # type: ignore[arg-type]
        answers=answers,  # type: ignore[arg-type]
    )
    return agent, posts, search, answers


def memory(rewritten: str = "") -> MemoryContext:
    return MemoryContext(rewritten_query=rewritten)


# ── 라우팅 ──────────────────────────────────────────────────────────
async def test_list_posts_does_not_read_bodies() -> None:
    """목록은 제목과 링크면 된다. 본문을 읽으면 느리고 비싸다."""
    agent, posts, _, _ = build(ChatPlan(task="list_posts"))

    result = await agent.run("목록 보여줘", memory())

    assert result.intent == "list_posts"
    assert posts.hydrated is False


@pytest.mark.parametrize("task", ["summarize_posts", "answer_from_posts"])
async def test_content_tasks_read_bodies(task: str) -> None:
    agent, posts, _, answers = build(ChatPlan(task=task))  # type: ignore[arg-type]

    await agent.run("정리해줘", memory())

    assert posts.hydrated is True
    assert "본문 id1" in answers.seen[0].context


async def test_general_rag_searches_without_constraints() -> None:
    agent, _, search, _ = build(ChatPlan(task="general_rag"))

    await agent.run("Kafka가 뭐야", memory())

    assert search.calls == [("Kafka가 뭐야", False)]


async def test_semantic_search_passes_constraints() -> None:
    agent, _, search, _ = build(ChatPlan(task="semantic_search_posts"))

    await agent.run("검색", memory())

    assert search.calls[0][1] is True


async def test_a_scoped_semantic_search_uses_metadata_lookup_instead() -> None:
    """벡터 검색은 날짜·블로그 조건을 지키지 못한다."""
    plan = ChatPlan(
        task="semantic_search_posts",
        strict_scope=True,
        constraints=PostConstraints(tags=["Kafka"]),
    )
    agent, posts, search, _ = build(plan)

    await agent.run("지난달 Kafka 글", memory())

    assert search.calls == []
    assert posts.hydrated is True


async def test_no_result_task_short_circuits() -> None:
    agent, _, search, answers = build(ChatPlan(task="no_result"))

    result = await agent.run("불가능한 조건", memory())

    assert search.calls == []
    assert answers.seen[0].status == "no_result"
    assert result.intent == "no_result"


async def test_strict_scope_with_no_matches_skips_reading_bodies() -> None:
    plan = ChatPlan(
        task="summarize_posts", strict_scope=True, constraints=PostConstraints(tags=["Nope"])
    )
    agent, posts, _, _ = build(plan, posts=FakePosts(ToolResult(status="no_result")))

    await agent.run("정리해줘", memory())

    assert posts.hydrated is False


async def test_the_rewritten_query_drives_the_search() -> None:
    agent, _, search, _ = build(ChatPlan(task="general_rag"))

    await agent.run("그건 왜 그래?", memory(rewritten="Kafka 리밸런싱 원인"))

    assert search.calls[0][0] == "Kafka 리밸런싱 원인"


# ── 진행 상황 ───────────────────────────────────────────────────────
async def test_activities_are_streamed_and_collapsed() -> None:
    seen: list[Activity] = []

    async def sink(activity: Activity) -> None:
        seen.append(activity)

    agent, _, _, _ = build(ChatPlan(task="list_posts"))
    result = await agent.run("목록", memory(), sink)

    # 스트림에는 running/completed가 모두 흐른다.
    assert [a.status for a in seen] == ["running", "completed"] * 3
    # 최종 목록은 종류마다 한 줄이고 전부 완료 상태다.
    assert [a["type"] for a in result.activities] == ["plan", "list_posts", "answer"]
    assert {a["status"] for a in result.activities} == {"completed"}


async def test_activities_have_korean_labels() -> None:
    agent, _, _, _ = build(ChatPlan(task="general_rag"))

    result = await agent.run("질문", memory())

    assert all(activity["label"] for activity in result.activities)


async def test_concurrent_runs_do_not_share_activity_state() -> None:
    """에이전트는 프로세스마다 하나다. 실행 상태를 self에 두면 섞인다."""
    agent, _, _, _ = build(ChatPlan(task="general_rag"))

    results = await asyncio.gather(*(agent.run(f"질문{i}", memory()) for i in range(8)))

    # 실행마다 plan → search → answer 세 줄. 공유되면 24줄이 한 곳에 쌓인다.
    assert [[a["type"] for a in r.activities] for r in results] == [
        ["plan", "search", "answer"]
    ] * 8


# ── 출력 가드 ───────────────────────────────────────────────────────
async def test_a_leaking_answer_is_replaced_and_sources_dropped() -> None:
    agent, _, _, _ = build(
        ChatPlan(task="list_posts"), answers=FakeAnswers("### FINAL REMINDER 내부 규칙")
    )

    result = await agent.run("목록", memory())

    assert "FINAL REMINDER" not in result.answer
    assert result.sources == []
    assert result.guard["action"] == "block"


async def test_a_clean_answer_keeps_its_sources() -> None:
    agent, _, _, _ = build(ChatPlan(task="list_posts"))

    result = await agent.run("목록", memory())

    assert result.sources[0]["post_id"] == "id1"
    assert result.guard == {}


# ── 답변 조립 ───────────────────────────────────────────────────────
class RecordingLlm:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, purpose, system, user, **kwargs):
        self.calls += 1
        return "모델 답변", "m"


async def test_list_answers_are_built_without_calling_a_model() -> None:
    """링크를 지어내거나 개수를 틀리는 것을 원천 차단한다."""
    llm = RecordingLlm()
    result = ToolResult(status="ok", posts=[record(1), record(2)], total=7, message="조회했습니다.")

    answer = await AnswerGenerator(llm).generate(  # type: ignore[arg-type]
        "목록", ChatPlan(task="list_posts"), result, {}
    )

    assert llm.calls == 0
    assert "전체 7개 중 2개입니다" in answer
    assert "[제목1](https://blog.test/1)" in answer
    assert "태그: Kafka" in answer


async def test_no_result_answers_skip_the_model() -> None:
    llm = RecordingLlm()

    answer = await AnswerGenerator(llm).generate(  # type: ignore[arg-type]
        "질문", ChatPlan(task="general_rag"), ToolResult(status="no_result"), {}
    )

    assert llm.calls == 0
    assert answer == NO_RESULT_MESSAGE


async def test_a_failed_tool_does_not_reach_the_model() -> None:
    llm = RecordingLlm()

    answer = await AnswerGenerator(llm).generate(  # type: ignore[arg-type]
        "질문", ChatPlan(task="general_rag"), ToolResult(status="failed", message="검색 실패"), {}
    )

    assert llm.calls == 0
    assert answer == "검색 실패"


async def test_the_context_is_clipped_before_it_reaches_the_model() -> None:
    captured: dict[str, str] = {}

    class Capturing(RecordingLlm):
        async def complete(self, purpose, system, user, **kwargs):
            captured["user"] = user
            return "답변", "m"

    result = ToolResult(status="ok", context="가" * 5000)
    await AnswerGenerator(Capturing(), max_context_chars=100).generate(  # type: ignore[arg-type]
        "질문", ChatPlan(task="general_rag"), result, {}
    )

    assert "가" * 101 not in captured["user"]


def test_an_empty_post_list_reports_no_result() -> None:
    assert format_post_list(ToolResult(status="ok")) == NO_RESULT_MESSAGE


def test_post_context_prefers_the_body_over_the_summary() -> None:
    post = record(1)
    post.plain_text = "전체 본문"

    context = build_post_context([post])

    assert "전체 본문" in context
    assert "요약1" not in context


def test_post_context_falls_back_to_the_summary() -> None:
    assert "요약1" in build_post_context([record(1)])


def test_post_context_handles_a_post_with_neither() -> None:
    post = record(1)
    post.summary = ""

    assert "본문/요약 없음" in build_post_context([post])
