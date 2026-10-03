"""주제 목록·태그 정리·주제 재분류."""

from __future__ import annotations

from techletter.explainer.prompt import SYSTEM_PROMPT
from techletter.summary.classifier import TOPIC_CLASSIFY_INSTRUCTION, TopicClassifier
from techletter.summary.topics import OTHER, TOPIC_NAMES, TOPICS, normalize_tags, normalize_topics


class FakeLlm:
    def __init__(self, payload: dict, model: str = "nvidia/nemotron:free") -> None:
        self.payload = payload
        self.model = model
        self.calls: list[dict] = []

    async def complete_json(self, purpose, system, user, **kwargs) -> tuple[dict, str]:
        self.calls.append({"purpose": purpose, "user": user})
        return self.payload, self.model


def test_the_prompts_list_every_topic() -> None:
    for topic in TOPICS:
        assert f"{topic.slug} | {topic.name}" in SYSTEM_PROMPT
        assert f"{topic.slug} | {topic.name}" in TOPIC_CLASSIFY_INSTRUCTION


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


# ── 주제 재분류 ─────────────────────────────────────────────────────
async def test_topics_are_classified_in_one_call() -> None:
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

    result = await TopicClassifier(llm).classify_topics(posts)  # type: ignore[arg-type]

    assert result == {"a": ["보안·인증", "LLM 활용·프롬프트"], "b": [OTHER]}  # c는 누락
