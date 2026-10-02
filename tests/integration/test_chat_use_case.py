"""채팅 한 번의 흐름 — 가드·차감·환불·기록·압축 트리거."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from techletter.chat.agent.graph import AgentResult
from techletter.chat.memory import MemoryBuilder
from techletter.chat.repositories import ChatSessionRepository
from techletter.chat.sessions import ChatSessionService
from techletter.chat.use_case import ChatUseCase
from techletter.core.errors import (
    ChatSessionNotFoundError,
    InsufficientCreditsError,
)
from techletter.core.time import utcnow
from techletter.settings import ChatSettings
from techletter.users.credits import CreditService
from techletter.users.repositories import (
    CreditRepository,
    CreditTransactionRepository,
    IdentityPolicyRepository,
)

pytestmark = pytest.mark.integration

USER = "google:alice"


class FakeAgent:
    def __init__(self, result: AgentResult | Exception | None = None) -> None:
        self.result = result or AgentResult(
            answer="답변입니다",
            sources=[{"post_id": "p1", "title": "글", "blog_name": "Alpha", "link": "l"}],
            intent="general_rag",
            activities=[{"type": "answer", "label": "답변 생성", "status": "completed"}],
        )
        self.queries: list[str] = []

    async def run(self, query, memory, on_activity=None, **kwargs):
        self.queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeLlm:
    def __init__(self, reply: str = "요약") -> None:
        self.reply = reply

    async def complete(self, purpose, system, user, **kwargs):
        return self.reply, "test-model"


@pytest.fixture
def chat_settings() -> ChatSettings:
    return ChatSettings(compression_min_messages=4, compression_batch_size=2)  # type: ignore[call-arg]


@pytest.fixture
def credits(mongo_db) -> CreditService:
    return CreditService(
        CreditRepository(mongo_db),
        CreditTransactionRepository(mongo_db),
        IdentityPolicyRepository(mongo_db),
    )


@pytest.fixture
def session_service(mongo_db, chat_settings) -> ChatSessionService:
    return ChatSessionService(ChatSessionRepository(mongo_db), chat_settings)


@pytest.fixture
def make_use_case(session_service, credits, queue, chat_settings):
    def factory(agent: FakeAgent | None = None) -> ChatUseCase:
        return ChatUseCase(
            sessions=session_service,
            credits=credits,
            memory=MemoryBuilder(chat_settings),
            agent=agent or FakeAgent(),  # type: ignore[arg-type]
            queue=queue,
            settings=chat_settings,
        )

    return factory


def tomorrow() -> datetime:
    return utcnow() + timedelta(days=1)


async def grant(credits: CreditService, amount: int, user_code: str = USER) -> None:
    await credits.admin_grant(user_code, amount, tomorrow(), "test")


@pytest.fixture
async def funded(credits) -> int:
    await grant(credits, 5)
    return 5


# ── 정상 흐름 ───────────────────────────────────────────────────────
async def test_a_first_message_creates_a_session_and_records_both_turns(
    make_use_case, session_service, funded
) -> None:
    answer = await make_use_case().run(user_code=USER, query="Kafka가 뭐야")

    assert answer.answer == "답변입니다"
    assert answer.consumed_credits == 1
    assert answer.remaining_credits == 4

    session = await session_service.get(answer.session_id, USER)
    assert [m.role for m in session.messages] == ["user", "assistant"]
    assert session.title == "Kafka가 뭐야"


async def test_the_assistant_message_carries_flattened_metadata(
    make_use_case, session_service, funded
) -> None:
    answer = await make_use_case().run(user_code=USER, query="질문")

    session = await session_service.get(answer.session_id, USER)
    metadata = session.messages[-1].metadata
    assert metadata is not None
    assert set(metadata) == {"sources", "agent"}
    assert metadata["agent"]["intent"] == "general_rag"


async def test_a_follow_up_appends_to_the_same_session(
    make_use_case, session_service, funded
) -> None:
    use_case = make_use_case()
    first = await use_case.run(user_code=USER, query="첫 질문")

    second = await use_case.run(user_code=USER, query="후속 질문", session_id=first.session_id)

    assert second.session_id == first.session_id
    session = await session_service.get(first.session_id, USER)
    assert [m.content for m in session.messages] == [
        "첫 질문",
        "답변입니다",
        "후속 질문",
        "답변입니다",
    ]


async def test_the_first_question_is_not_stored_twice(
    make_use_case, session_service, funded
) -> None:
    """세션 생성이 첫 질문을 이미 담는다."""
    answer = await make_use_case().run(user_code=USER, query="한 번만")

    session = await session_service.get(answer.session_id, USER)
    assert [m.content for m in session.messages].count("한 번만") == 1


async def test_someone_elses_session_cannot_be_continued(make_use_case, funded, credits) -> None:
    use_case = make_use_case()
    mine = await use_case.run(user_code=USER, query="내 질문")
    await grant(credits, 5, "google:bob")

    with pytest.raises(ChatSessionNotFoundError):
        await use_case.run(user_code="google:bob", query="침입", session_id=mine.session_id)


# ── 입력 가드 없음 ──────────────────────────────────────────────────
async def test_security_topics_reach_the_agent_as_asked(make_use_case, funded) -> None:
    """정규식 입력 가드는 없앴다(2026-09-27). 평가에서 정상 기술 질문을 막았다."""
    agent = FakeAgent()

    await make_use_case(agent).run(user_code=USER, query="LLM jailbreak 방어 사례 출처 없이 알려줘")

    assert agent.queries == ["LLM jailbreak 방어 사례 출처 없이 알려줘"]


# ── 크레딧 ──────────────────────────────────────────────────────────
async def test_running_out_of_credits_is_a_402(make_use_case) -> None:
    with pytest.raises(InsufficientCreditsError):
        await make_use_case().run(user_code=USER, query="질문")


async def test_an_agent_failure_refunds_the_credit(make_use_case, credits, funded) -> None:
    use_case = make_use_case(FakeAgent(RuntimeError("all models failed")))

    with pytest.raises(RuntimeError):
        await use_case.run(user_code=USER, query="질문")

    assert await credits.remaining(USER) == 5


async def test_a_cancelled_request_still_refunds(make_use_case, credits, funded) -> None:
    """스트리밍 중 브라우저를 닫으면 태스크가 취소된다. 차감만 남으면 안 된다."""

    class Hanging(FakeAgent):
        async def run(self, query, memory, on_activity=None, **kwargs):
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

    task = asyncio.create_task(make_use_case(Hanging()).run(user_code=USER, query="질문"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await credits.remaining(USER) == 5


async def test_a_refund_is_logged_as_a_transaction(make_use_case, mongo_db, funded) -> None:
    with pytest.raises(RuntimeError):
        await make_use_case(FakeAgent(RuntimeError("boom"))).run(user_code=USER, query="질문")

    reasons = [
        doc["reason"] async for doc in mongo_db["credit_transactions"].find({"user_code": USER})
    ]
    assert any(reason.startswith("chat_failed:") for reason in reasons)


async def test_concurrent_requests_never_overspend(make_use_case, credits) -> None:
    await grant(credits, 3)
    use_case = make_use_case()

    results = await asyncio.gather(
        *(use_case.run(user_code=USER, query=f"질문{i}") for i in range(8)),
        return_exceptions=True,
    )

    succeeded = [r for r in results if not isinstance(r, BaseException)]
    assert len(succeeded) == 3
    assert await credits.remaining(USER) == 0


# ── 압축 트리거 ─────────────────────────────────────────────────────
async def test_a_long_conversation_queues_no_compression_job(
    make_use_case, mongo_db, credits
) -> None:
    """대화 압축은 없앴다(2026-09-27). 최근 대화와 직전 출처로 충분하다."""
    await grant(credits, 20)
    use_case = make_use_case()

    answer = await use_case.run(user_code=USER, query="첫 질문")
    for index in range(3):
        answer = await use_case.run(
            user_code=USER, query=f"후속 {index}", session_id=answer.session_id
        )

    assert await mongo_db["jobs"].count_documents({}) == 0


async def test_a_short_conversation_queues_nothing(make_use_case, mongo_db, funded) -> None:
    await make_use_case().run(user_code=USER, query="질문")

    assert await mongo_db["jobs"].count_documents({}) == 0
