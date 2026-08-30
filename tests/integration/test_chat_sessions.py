"""세션 저장소와 서비스."""

from __future__ import annotations

import asyncio

import pytest

from techletter.chat.models import ChatSession, SessionMemory
from techletter.chat.repositories import ChatSessionRepository, SuggestedQuestionRepository
from techletter.chat.sessions import ChatSessionService
from techletter.chat.suggested_questions import SuggestedQuestionService
from techletter.core.errors import (
    ChatSessionNotFoundError,
    InvalidRequestError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from techletter.core.pagination import Page
from techletter.settings import ChatSettings

pytestmark = pytest.mark.integration

USER = "google:alice"
OTHER = "google:bob"


@pytest.fixture
def repo(mongo_db) -> ChatSessionRepository:
    return ChatSessionRepository(mongo_db)


@pytest.fixture
def sessions(repo) -> ChatSessionService:
    settings = ChatSettings(compression_min_messages=6, compression_batch_size=3)  # type: ignore[call-arg]
    return ChatSessionService(repo, settings)


# ── 생성·조회 ───────────────────────────────────────────────────────
async def test_a_new_session_takes_its_title_from_the_first_message(sessions) -> None:
    session = await sessions.create(USER, "Kafka 리밸런싱 알려줘")

    assert session.title == "Kafka 리밸런싱 알려줘"
    assert [m.content for m in session.messages] == ["Kafka 리밸런싱 알려줘"]


async def test_an_empty_session_uses_the_default_title(sessions) -> None:
    session = await sessions.create(USER)

    assert session.title == "New Chat"
    assert session.messages == []


async def test_another_users_session_is_not_found(sessions) -> None:
    session = await sessions.create(USER, "질문")

    with pytest.raises(ChatSessionNotFoundError):
        await sessions.get(str(session.id), OTHER)


async def test_a_malformed_session_id_is_not_found(sessions) -> None:
    with pytest.raises(ChatSessionNotFoundError):
        await sessions.get("not-an-id", USER)


# ── 목록 ────────────────────────────────────────────────────────────
async def test_the_list_carries_counts_but_not_message_bodies(sessions) -> None:
    """메시지 본문은 빼도 개수는 프론트가 알 수 있어야 한다."""
    session = await sessions.create(USER, "첫 질문")
    await sessions.append(session, "assistant", "답변")

    rows, total = await sessions.list(USER, Page(1, 10))

    assert total == 1
    assert rows[0].message_count == 2
    assert rows[0].session.messages == []


async def test_the_list_is_newest_updated_first(sessions) -> None:
    first = await sessions.create(USER, "오래된")
    await sessions.create(USER, "새것")
    await sessions.append(first, "assistant", "다시 갱신")

    rows, _ = await sessions.list(USER, Page(1, 10))

    assert [row.session.title for row in rows] == ["오래된", "새것"]


async def test_the_list_only_shows_your_own_sessions(sessions) -> None:
    await sessions.create(USER, "내 것")
    await sessions.create(OTHER, "남의 것")

    rows, total = await sessions.list(USER, Page(1, 10))

    assert total == 1
    assert rows[0].session.title == "내 것"


async def test_list_pagination(sessions) -> None:
    for index in range(5):
        await sessions.create(USER, f"질문 {index}")

    rows, total = await sessions.list(USER, Page(2, 2))

    assert total == 5
    assert len(rows) == 2


# ── 메시지 ──────────────────────────────────────────────────────────
async def test_appending_bumps_the_update_time(sessions) -> None:
    session = await sessions.create(USER, "질문")
    before = session.updated_at
    # Mongo의 시각 정밀도는 밀리초다. 같은 밀리초 안에서 끝나면 값이 같아진다.
    await asyncio.sleep(0.01)

    updated = await sessions.append(session, "assistant", "답변")

    assert updated.updated_at > before


async def test_the_title_is_set_by_the_first_user_message_only(sessions) -> None:
    session = await sessions.create(USER)

    after_first = await sessions.append(session, "user", "첫 질문입니다")
    after_second = await sessions.append(after_first, "user", "두 번째")

    assert after_first.title == "첫 질문입니다"
    assert after_second.title == "첫 질문입니다"


async def test_message_metadata_round_trips(sessions) -> None:
    session = await sessions.create(USER, "질문")

    updated = await sessions.append(
        session,
        "assistant",
        "답변",
        metadata={"sources": [{"post_id": "p1"}], "agent": {"intent": "general_rag"}},
    )

    assert updated.messages[-1].metadata is not None
    assert updated.messages[-1].metadata["agent"]["intent"] == "general_rag"


# ── 삭제 ────────────────────────────────────────────────────────────
async def test_deleting_someone_elses_session_fails(sessions) -> None:
    session = await sessions.create(USER, "질문")

    with pytest.raises(ChatSessionNotFoundError):
        await sessions.delete(str(session.id), OTHER)

    assert await sessions.get(str(session.id), USER) is not None


async def test_deleting_a_user_removes_every_session(sessions) -> None:
    await sessions.create(USER, "a")
    await sessions.create(USER, "b")
    await sessions.create(OTHER, "c")

    deleted = await sessions.delete_all(USER)

    assert deleted == 2
    _, remaining = await sessions.list(OTHER, Page(1, 10))
    assert remaining == 1


# ── 메모리 압축 ─────────────────────────────────────────────────────
def make_session(count: int, memory: SessionMemory | None = None) -> ChatSession:
    session = ChatSession.start(USER, "첫 질문")
    session.messages = session.messages * count
    session.memory = memory
    return session


def test_a_short_conversation_does_not_need_compression(sessions) -> None:
    assert sessions.needs_compression(make_session(5)) is False


def test_a_long_conversation_needs_compression(sessions) -> None:
    assert sessions.needs_compression(make_session(6)) is True


def test_a_pending_compression_is_not_requested_again(sessions) -> None:
    session = make_session(20, SessionMemory(status="pending"))

    assert sessions.needs_compression(session) is False


def test_compression_waits_for_a_full_batch(sessions) -> None:
    covered = SessionMemory(summary="s", covered_message_count=6, status="completed")

    assert sessions.needs_compression(make_session(8, covered)) is False
    assert sessions.needs_compression(make_session(9, covered)) is True


async def test_claiming_compression_is_exclusive(sessions, repo) -> None:
    session = await sessions.create(USER, "질문")

    first = await sessions.claim_compression(str(session.id))
    second = await sessions.claim_compression(str(session.id))

    assert (first, second) == (True, False)
    stored = await repo.get(str(session.id))
    assert stored is not None and stored.memory is not None
    assert stored.memory.status == "pending"
    assert stored.memory.requested_at is not None


async def test_claiming_preserves_the_previous_summary(sessions, repo) -> None:
    """압축이 끝나기 전까지는 직전 요약으로 답해야 한다."""
    session = await sessions.create(USER, "질문")
    await sessions.store_summary(str(session.id), "이전 요약", 4)

    await sessions.claim_compression(str(session.id))

    stored = await repo.get(str(session.id))
    assert stored is not None and stored.memory is not None
    assert stored.memory.summary == "이전 요약"
    assert stored.memory.covered_message_count == 4


async def test_storing_a_summary_does_not_reorder_the_session_list(sessions, repo) -> None:
    """압축은 백그라운드 잡이다. 사용자가 만지지 않은 세션이 목록 위로 올라오면 안 된다."""
    session = await sessions.create(USER, "질문")
    before = (await repo.get(str(session.id))).updated_at  # type: ignore[union-attr]

    await sessions.store_summary(str(session.id), "요약", 4)

    after = (await repo.get(str(session.id))).updated_at  # type: ignore[union-attr]
    assert after == before


async def test_a_failed_compression_keeps_the_old_summary(sessions, repo) -> None:
    session = await sessions.create(USER, "질문")
    await sessions.store_summary(str(session.id), "쓸만한 요약", 4)
    stored = await repo.get(str(session.id))

    await sessions.mark_compression_failed(str(session.id), "boom", stored.memory)  # type: ignore[union-attr]

    after = await repo.get(str(session.id))
    assert after is not None and after.memory is not None
    assert after.memory.status == "failed"
    assert after.memory.summary == "쓸만한 요약"
    assert after.memory.error_message == "boom"


# ── 추천 질문 ───────────────────────────────────────────────────────
@pytest.fixture
def questions(mongo_db) -> SuggestedQuestionService:
    return SuggestedQuestionService(SuggestedQuestionRepository(mongo_db))


async def test_creating_assigns_increasing_sort_orders(questions) -> None:
    first = await questions.create("첫 질문")
    second = await questions.create("두 번째 질문")

    assert (first.sort_order, second.sort_order) == (10, 20)


async def test_whitespace_is_collapsed(questions) -> None:
    question = await questions.create("  여러   공백이   있는  질문 ")

    assert question.text == "여러 공백이 있는 질문"


async def test_duplicates_are_rejected_by_the_unique_index(questions) -> None:
    """앱 레벨 검사만으로는 동시 요청 두 개를 막지 못한다."""
    await questions.create("같은 질문")

    with pytest.raises(ResourceConflictError):
        await questions.create("  같은   질문  ")


async def test_case_differences_still_count_as_duplicates(questions) -> None:
    await questions.create("Kafka Question")

    with pytest.raises(ResourceConflictError):
        await questions.create("kafka question")


async def test_an_empty_question_is_rejected(questions) -> None:
    with pytest.raises(InvalidRequestError):
        await questions.create("   ")


async def test_an_overlong_question_is_rejected(questions) -> None:
    with pytest.raises(InvalidRequestError):
        await questions.create("가" * 501)


async def test_the_list_hides_inactive_questions_by_default(questions) -> None:
    await questions.create("보이는 질문")
    hidden = await questions.create("숨은 질문")
    await questions.update(str(hidden.id), is_active=False)

    visible = await questions.list()
    every = await questions.list(include_inactive=True)

    assert [q.text for q in visible] == ["보이는 질문"]
    assert len(every) == 2


async def test_the_list_is_ordered_by_sort_order(questions) -> None:
    await questions.create("세 번째", sort_order=30)
    await questions.create("첫 번째", sort_order=10)
    await questions.create("두 번째", sort_order=20)

    assert [q.text for q in await questions.list()] == ["첫 번째", "두 번째", "세 번째"]


async def test_updating_only_the_flag_keeps_the_sort_order(questions) -> None:
    """전체 교체로 처리하면 순번을 안 보냈을 때 0으로 밀린다."""
    question = await questions.create("질문", sort_order=50)

    updated = await questions.update(str(question.id), is_active=False)

    assert updated.sort_order == 50
    assert updated.text == "질문"


async def test_updating_text_updates_the_duplicate_key(questions) -> None:
    question = await questions.create("원래 질문")

    await questions.update(str(question.id), text="바뀐 질문")

    with pytest.raises(ResourceConflictError):
        await questions.create("바뀐 질문")


async def test_a_question_can_keep_its_own_text_on_update(questions) -> None:
    question = await questions.create("그대로")

    updated = await questions.update(str(question.id), text="그대로", sort_order=99)

    assert updated.sort_order == 99


async def test_updating_an_unknown_question_is_not_found(questions) -> None:
    with pytest.raises(ResourceNotFoundError):
        await questions.update("507f1f77bcf86cd799439011", text="x")


async def test_deleting_an_unknown_question_is_not_found(questions) -> None:
    with pytest.raises(ResourceNotFoundError):
        await questions.delete("507f1f77bcf86cd799439011")
