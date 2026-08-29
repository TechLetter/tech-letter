"""저장되는 문서의 모양 — 05 §1.5 스키마와 정확히 같아야 한다.

모델을 통해 읽으면 낯선 필드가 조용히 무시되므로, 이 검사는 `to_mongo()`가
내놓는 dict를 직접 본다.
"""

from __future__ import annotations

from techletter.chat.models import ChatMessage, ChatSession, SessionMemory
from techletter.content.models import AISummary, Blog, EmbeddingMeta, Post, StatusFlags

POST_FIELDS = {
    "created_at",
    "updated_at",
    "blog_id",
    "blog_name",
    "title",
    "link",
    "published_at",
    "thumbnail_url",
    "view_count",
    "status",
    "aisummary",
    "plain_text",
    "embedding",
}


def test_post_writes_exactly_the_documented_fields() -> None:
    assert set(Post().to_mongo()) == POST_FIELDS


def test_id_is_not_written_on_insert() -> None:
    assert "_id" not in Post().to_mongo()


def test_nested_documents_carry_no_id_or_timestamps() -> None:
    """`BaseDocument`를 중첩에 쓰면 `status`에 `_id: null`이 박힌다."""
    doc = Post(status=StatusFlags(), aisummary=AISummary()).to_mongo()

    assert set(doc["status"]) == {"ai_summarized", "embedded", "failed_reason"}
    assert set(doc["aisummary"]) == {
        "categories",
        "tags",
        "summary",
        "model_name",
        "generated_at",
    }


def test_embedding_metadata_shape() -> None:
    meta = EmbeddingMeta(model_name="m", collection_name="c", vector_dimension=3)

    assert set(meta.to_mongo()) == {
        "model_name",
        "collection_name",
        "vector_dimension",
        "chunk_count",
        "embedded_at",
    }


def test_blog_writes_the_documented_fields_plus_the_new_ones() -> None:
    doc = Blog().to_mongo()

    assert {"name", "url", "rss_url", "blog_type", "is_active"} <= set(doc)
    # 신규 필드. 기존 문서에 없어도 기본값으로 읽힌다.
    assert {"consecutive_failures", "tls_insecure"} <= set(doc)
    assert "_id" not in doc


def test_chat_message_keeps_created_at_only() -> None:
    assert set(ChatMessage().to_mongo()) == {"role", "content", "created_at", "metadata"}


def test_session_memory_shape() -> None:
    assert set(SessionMemory().to_mongo()) == {
        "summary",
        "covered_message_count",
        "status",
        "requested_at",
        "updated_at",
        "error_message",
    }


def test_chat_session_shape() -> None:
    session = ChatSession.start("google:abc", "첫 질문")
    doc = session.to_mongo()

    assert set(doc) == {"created_at", "updated_at", "user_code", "title", "messages", "memory"}
    assert set(doc["messages"][0]) == {"role", "content", "created_at", "metadata"}


def test_a_long_first_message_is_clipped_into_the_title() -> None:
    session = ChatSession.start("google:abc", "가" * 40)

    assert session.title == "가" * 30 + "..."


def test_a_short_first_message_becomes_the_title_verbatim() -> None:
    assert ChatSession.start("google:abc", "Kafka 질문").title == "Kafka 질문"


def test_a_session_without_a_first_message_uses_the_default_title() -> None:
    session = ChatSession.start("google:abc")

    assert session.title == "New Chat"
    assert session.messages == []
