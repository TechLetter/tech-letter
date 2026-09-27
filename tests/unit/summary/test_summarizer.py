"""요약 후처리 — 프롬프트로 지켜지지 않는 제약을 코드가 보장한다."""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError
from techletter.settings import SummarySettings
from techletter.summary.summarizer import (
    SYSTEM_INSTRUCTION,
    TOPIC_CLASSIFY_INSTRUCTION,
    Summarizer,
    clip_to_sentence,
    normalize_tags,
)
from techletter.summary.topics import OTHER, TOPIC_NAMES, TOPICS, normalize_topics


class FakeLlm:
    def __init__(self, payload: dict | Exception, model: str = "nvidia/nemotron:free") -> None:
        self.payload = payload
        self.model = model
        self.calls: list[dict] = []

    async def complete_json(self, purpose, system, user, **kwargs) -> tuple[dict, str]:
        self.calls.append({"purpose": purpose, "user": user})
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload, self.model


@pytest.fixture
def settings() -> SummarySettings:
    return SummarySettings()


def payload(**overrides) -> dict:
    return {
        "summary": "Kafka 리밸런싱의 원인과 대응을 정리한 글입니다.",
        "categories": ["streaming"],
        "tags": ["Kafka"],
        "error": None,
        **overrides,
    }


# ── 프롬프트 ────────────────────────────────────────────────────────
def test_the_prompt_declares_the_right_number_of_keys() -> None:
    """ "five keys"라고 쓰고 4개만 정의하면 모델이 다섯 번째 키를 환각한다."""
    assert "four keys" in SYSTEM_INSTRUCTION
    for key in ("summary", "categories", "tags", "error"):
        assert f'"{key}"' in SYSTEM_INSTRUCTION


def test_the_prompt_lists_every_topic() -> None:
    for topic in TOPICS:
        assert f"{topic.slug} | {topic.name}" in SYSTEM_INSTRUCTION
        assert f"{topic.slug} | {topic.name}" in TOPIC_CLASSIFY_INSTRUCTION


# ── 길이 후처리 ─────────────────────────────────────────────────────
def test_a_short_summary_is_left_alone() -> None:
    assert clip_to_sentence("짧은 요약입니다.", 200, 20) == "짧은 요약입니다."


def test_whitespace_is_collapsed() -> None:
    assert clip_to_sentence("여러   줄\n요약", 200, 20) == "여러 줄 요약"


def test_a_long_summary_is_cut_at_a_sentence_boundary() -> None:
    text = "첫 문장입니다. " * 40

    clipped = clip_to_sentence(text, 200, 20)

    assert len(clipped) <= 220
    assert clipped.endswith(".")


def test_a_summary_with_no_sentence_end_is_cut_with_an_ellipsis() -> None:
    clipped = clip_to_sentence("가" * 500, 200, 20)

    assert len(clipped) <= 221
    assert clipped.endswith("…")


def test_english_sentence_ends_are_recognized() -> None:
    clipped = clip_to_sentence("This is a sentence. " * 30, 200, 20)

    assert clipped.endswith(".")


# ── 주제·태그 후처리 ────────────────────────────────────────────────
def test_topics_outside_the_list_are_dropped() -> None:
    """`lfm-2.5-2.6b`가 Frontend 글을 Infrastructure로 분류한 실측이 있다."""
    assert normalize_topics(["frontend", "우주공학", "mobile"]) == ["프론트엔드", "모바일"]


def test_a_topic_may_come_back_as_its_name() -> None:
    assert normalize_topics(["  RAG·검색 ", "KUBERNETES"]) == ["RAG·검색", "쿠버네티스·컨테이너"]


def test_topics_fall_back_to_other() -> None:
    assert normalize_topics([]) == [OTHER]
    assert normalize_topics("nope") == [OTHER]
    assert normalize_topics(["Infrastructure"]) == [OTHER]  # 옛 카테고리 이름


def test_topics_are_capped_at_three() -> None:
    assert len(normalize_topics([t.slug for t in TOPICS])) == 3


def test_topic_names_are_unique() -> None:
    assert len(TOPIC_NAMES) == len(set(TOPIC_NAMES))
    assert len({t.slug for t in TOPICS}) == len(TOPICS)


def test_tags_are_deduped_case_insensitively() -> None:
    assert normalize_tags(["Kafka", "kafka", "Redis"], 7) == ["Kafka", "Redis"]


def test_tags_are_capped() -> None:
    assert len(normalize_tags([f"tag{i}" for i in range(20)], 7)) == 7


def test_absurdly_long_tags_are_dropped() -> None:
    assert normalize_tags(["Kafka", "x" * 100], 7) == ["Kafka"]


def test_non_list_tags_are_ignored() -> None:
    assert normalize_tags("Kafka", 7) == []


# ── 요약 호출 ───────────────────────────────────────────────────────
async def test_a_normal_summary_is_returned(settings) -> None:
    llm = FakeLlm(payload())

    result = await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert result.summary.startswith("Kafka")
    assert result.categories == ["메시징·스트리밍"]
    assert result.model_name == "nvidia/nemotron:free"
    assert result.truncated_input is False


async def test_an_error_field_is_a_permanent_failure(settings) -> None:
    llm = FakeLlm(payload(error="봇 차단 페이지입니다", summary=""))

    with pytest.raises(PermanentError) as excinfo:
        await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert excinfo.value.reason == "not_summarizable"


async def test_an_empty_summary_is_rejected_even_without_an_error(settings) -> None:
    """`error`만 보고 빈 요약을 통과시키면 안 된다."""
    llm = FakeLlm(payload(summary="   "))

    with pytest.raises(PermanentError) as excinfo:
        await Summarizer(llm, settings).summarize("본문")  # type: ignore[arg-type]

    assert excinfo.value.reason == "empty_summary"


async def test_a_huge_body_is_truncated(settings) -> None:
    settings.max_input_chars = 100
    llm = FakeLlm(payload())

    result = await Summarizer(llm, settings).summarize("가" * 5000)  # type: ignore[arg-type]

    assert result.truncated_input is True
    assert len(llm.calls[0]["user"]) == 100


# ── 주제 재분류 ─────────────────────────────────────────────────────
async def test_topics_are_classified_in_one_call(settings) -> None:
    llm = FakeLlm(
        {
            "results": [
                {"id": "a", "topics": ["security", "llm-apps"]},
                {"id": "b", "topics": ["없는-주제"]},
                {"id": "zzz", "topics": ["mobile"]},  # 묻지 않은 id는 버린다
            ]
        }
    )
    posts = [
        {"id": "a", "title": "t", "blog": "b", "summary": "s", "keywords": []},
        {"id": "b", "title": "t", "blog": "b", "summary": "s", "keywords": []},
        {"id": "c", "title": "t", "blog": "b", "summary": "s", "keywords": []},
    ]

    result = await Summarizer(llm, settings).classify_topics(posts)  # type: ignore[arg-type]

    assert result == {"a": ["보안·인증", "LLM 활용·프롬프트"], "b": [OTHER]}  # c는 누락
