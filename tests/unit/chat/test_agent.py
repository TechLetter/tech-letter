"""챗봇 에이전트 — 범위 읽기 → 근거 → 답변 1회."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from techletter.chat.agent import ChatAgent
from techletter.chat.agent.prompts import BRIEF_ANSWER_SYSTEM_PROMPT, NO_MATCH_ANSWER
from techletter.chat.agent.state import PostRecord, Source, ToolResult
from techletter.chat.memory import MemoryContext, Turn


def result(*ids: str) -> ToolResult:
    records = [
        PostRecord(
            id=i, title=f"제목 {i}", link=f"https://x/{i}", blog_name="Alpha", published_at=""
        )
        for i in ids
    ]
    return ToolResult(
        status="ok" if ids else "no_result",
        posts=records,
        context="\n".join(f"[{n}] {r.title}" for n, r in enumerate(records, 1)),
        sources=[
            Source(post_id=r.id, title=r.title, blog_name="Alpha", link=r.link) for r in records
        ],
        total=len(records),
    )


class FakeEvidence:
    def __init__(self, found: ToolResult | None = None) -> None:
        self.found = found if found is not None else result("p1", "p2")
        self.queries: list[tuple[str, Any, str | None]] = []
        self.scoped: list[tuple[str, list[str]]] = []
        self.ranked: list[tuple[str, int | None]] = []

    async def for_query(self, query, flt, *, client=None, boost_blog_id=None, **kwargs):
        self.queries.append((query, flt, boost_blog_id))
        return self.found

    async def for_posts(self, query, post_ids, *, client=None):
        self.scoped.append((query, post_ids))
        return self.found

    async def rank(self, query, flt, *, client=None, boost_blog_id=None, limit=None, **kwargs):
        self.ranked.append((query, limit))
        return [SimpleNamespace(id=i) for i in ("p1", "p2")], None


class FakePosts:
    def __init__(self) -> None:
        self.listed: list[Any] = []
        self.selected: list[list[str]] = []

    async def list_posts(self, constraints):
        self.listed.append(constraints)
        return result("p9")

    def records(self, posts, *, message=""):
        return result(*[p.id for p in posts])

    async def get_posts(self, post_ids):
        self.selected.append(post_ids)
        return result(*[p for p in post_ids if p.startswith("p")])


class FakeAnswers:
    def __init__(self, reply: str = "답변 [1]") -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def answer(self, query, found, recent, model_id=None):
        self.calls.append({"query": query, "recent": recent, "model_id": model_id})
        return self.reply, "answer-model"

    async def brief(self, query, found):
        self.calls.append({"query": query, "brief": True, "context": found.context})
        return self.reply, "brief-model"


class FakeBlogs:
    async def list_active(self):
        return [
            SimpleNamespace(id="b-kakao", name="카카오"),
            SimpleNamespace(id="b-toss", name="토스"),
        ]


def agent(
    evidence=None, posts=None, answers=None
) -> tuple[ChatAgent, FakeEvidence, FakePosts, FakeAnswers]:
    evidence = evidence or FakeEvidence()
    posts = posts or FakePosts()
    answers = answers or FakeAnswers()
    built = ChatAgent(
        evidence=evidence,  # type: ignore[arg-type]
        posts=posts,  # type: ignore[arg-type]
        answers=answers,  # type: ignore[arg-type]
        blogs=FakeBlogs(),  # type: ignore[arg-type]
    )
    return built, evidence, posts, answers


async def test_a_question_is_one_answer_call_over_the_evidence() -> None:
    chat, evidence, _, answers = agent()

    out = await chat.run("Kafka 리밸런싱 대응 사례", MemoryContext())

    assert len(answers.calls) == 1
    assert [s["post_id"] for s in out.sources] == ["p1", "p2"]
    assert out.intent == "general_rag"
    assert out.model_id == "answer-model"
    assert evidence.queries[0][0] == "Kafka 리밸런싱 대응 사례"


async def test_a_named_blog_filters_the_search() -> None:
    chat, evidence, _, _ = agent()

    await chat.run("카카오 블로그에서 Kafka 운영 경험 정리해줘", MemoryContext())

    assert evidence.queries[0][1].blog_id == "b-kakao"


async def test_a_bare_blog_name_boosts_without_filtering() -> None:
    chat, evidence, _, _ = agent()

    await chat.run("토스 결제 시스템 글 정리해줘", MemoryContext())

    _, flt, boost = evidence.queries[0]
    assert flt.blog_id is None
    assert boost == "b-toss"


async def test_a_reference_answers_inside_the_previous_sources() -> None:
    chat, evidence, _, _ = agent()
    memory = MemoryContext(previous_query="vLLM 사례", previous_source_ids=["p7", "p8"])

    out = await chat.run("거기서 KV 캐시는 어떻게 다뤘어?", memory)

    assert evidence.scoped == [("거기서 KV 캐시는 어떻게 다뤘어?", ["p7", "p8"])]
    assert evidence.queries == []
    assert out.intent == "answer_from_posts"


async def test_a_short_follow_up_searches_with_the_previous_question() -> None:
    chat, evidence, _, answers = agent()
    memory = MemoryContext(
        recent=[Turn("user", "MCP 서버 도입 사례"), Turn("assistant", "...")],
        previous_query="MCP 서버 도입 사례",
    )

    await chat.run("보안 문제는?", memory)

    assert evidence.queries[0][0] == "MCP 서버 도입 사례 보안 문제는?"
    # 답변에는 사용자가 쓴 질문 그대로와 최근 대화가 간다.
    assert answers.calls[0]["query"] == "보안 문제는?"
    assert len(answers.calls[0]["recent"]) == 2


async def test_a_scope_only_list_needs_no_llm() -> None:
    chat, _, posts, answers = agent()

    out = await chat.run("카카오 블로그 글 목록 5개 보여줘", MemoryContext())

    assert answers.calls == []
    assert posts.listed[0].blog_id == "b-kakao"
    assert posts.listed[0].limit == 5
    assert out.intent == "list_posts"
    assert "제목 p9" in out.answer


async def test_a_list_with_keywords_ranks_by_them() -> None:
    chat, evidence, posts, answers = agent()

    out = await chat.run("Debezium 관련 글 목록", MemoryContext())

    assert evidence.ranked[0][0] == "Debezium"
    assert posts.listed == []
    assert answers.calls == []
    assert [s["post_id"] for s in out.sources] == ["p1", "p2"]


async def test_nothing_found_in_a_scope_says_so_without_llm() -> None:
    chat, _, _, answers = agent(evidence=FakeEvidence(result()))

    out = await chat.run("지난달 카카오 블로그 Kafka 정리", MemoryContext())

    assert answers.calls == []
    assert out.intent == "no_result"
    assert "지난달 카카오 블로그" in out.answer
    assert out.sources == []


async def test_when_the_posts_do_not_answer_there_are_no_sources() -> None:
    chat, _, _, _ = agent(answers=FakeAnswers(NO_MATCH_ANSWER))

    out = await chat.run("오늘 서울 날씨 어때?", MemoryContext())

    assert out.answer == NO_MATCH_ANSWER
    assert out.sources == []
    assert out.intent == "no_result"


async def test_the_chosen_model_reaches_the_answer() -> None:
    chat, _, _, answers = agent()

    await chat.run("Kafka", MemoryContext(), model_id="qwen/free")

    assert answers.calls[0]["model_id"] == "qwen/free"


# ── 검색 결과 AI 요약(post_ids) ─────────────────────────────────────
async def test_selected_posts_use_the_brief_path() -> None:
    chat, evidence, posts, answers = agent()

    out = await chat.run("요약", MemoryContext(), post_ids=["p1", "p2", "p3", "p4", "p5", "p6"])

    assert posts.selected == [["p1", "p2", "p3", "p4", "p5"]]
    assert answers.calls[0]["brief"] is True
    assert evidence.queries == []
    assert [s["post_id"] for s in out.sources] == ["p1", "p2", "p3", "p4", "p5"]


async def test_a_leaked_brief_prompt_is_blocked() -> None:
    leak = BRIEF_ANSWER_SYSTEM_PROMPT.splitlines()[0]
    chat, _, _, _ = agent(answers=FakeAnswers(leak))

    out = await chat.run("요약", MemoryContext(), post_ids=["p1"])

    assert out.sources == []
    assert out.guard


async def test_a_topic_list_filters_by_the_topic() -> None:
    chat, evidence, posts, _ = agent()

    await chat.run("MCP 관련 글 목록", MemoryContext())

    assert evidence.ranked == []
    assert "AI 에이전트·MCP" in posts.listed[0].categories


async def test_list_filler_words_are_not_search_terms() -> None:
    """평가 q05·q06: "에 올라온"이 검색어로 남아 최신순 목록이 아니었다."""
    chat, evidence, posts, _ = agent()

    await chat.run("카카오 블로그에 올라온 글 목록 보여줘", MemoryContext())
    await chat.run("최근에 올라온 글 5개만 알려줘", MemoryContext())

    assert evidence.ranked == []
    assert posts.listed[0].blog_id == "b-kakao"
    assert posts.listed[1].limit == 5


async def test_a_follow_up_with_its_own_terms_searches_alone() -> None:
    chat, evidence, _, _ = agent()
    memory = MemoryContext(previous_query="사내 MCP 서버 도입 사례", previous_source_ids=["p1"])

    await chat.run("그런 MCP 서버들에 보안 문제는 없었어?", memory)

    assert evidence.queries[0][0] == "그런 MCP 서버들에 보안 문제는 없었어?"


async def test_an_unknown_blog_is_answered_without_search() -> None:
    chat, evidence, posts, answers = agent()

    out = await chat.run("우아한형제들 블로그 글 목록", MemoryContext())

    assert "우아한형제들" in out.answer
    assert out.intent == "no_result"
    assert (evidence.queries, posts.listed, answers.calls) == ([], [], [])


async def test_an_answer_opening_with_no_match_drops_the_sources() -> None:
    """평가 q01·q21: 모델이 "찾지 못했습니다" 뒤에 설명을 붙여도 없는 것이다."""
    chat, _, _, _ = agent(
        answers=FakeAnswers(f"{NO_MATCH_ANSWER} 다만 CDC 사례는 있습니다 [1][2].")
    )

    out = await chat.run("Rockset 사례 있어?", MemoryContext())

    assert out.sources == []
    assert out.intent == "no_result"
    # 설명은 남기고, 출처가 없으니 번호는 지운다(채점에서 한 줄 답이 성의 없다고 나왔다).
    assert out.answer == f"{NO_MATCH_ANSWER} 다만 CDC 사례는 있습니다."
