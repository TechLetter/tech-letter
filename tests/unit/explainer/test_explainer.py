"""쉽게 읽기 — 분량 비례, 코드 검사, 한 번 재생성, 요약 잡 연결."""

from __future__ import annotations

import pytest

from techletter.content.jobs import PostRefPayload
from techletter.core.errors import PermanentError
from techletter.core.jobs.models import Job
from techletter.core.jobs.types import JobType
from techletter.explainer.checks import check, clean_body, feedback
from techletter.explainer.generator import ExplainerGenerator, reading_minutes
from techletter.explainer.models import Explainer
from techletter.explainer.prompt import SYSTEM_PROMPT, target_chars
from techletter.summary.handlers import SummaryRequestedHandler

# 목표 분량이 하한(1,500자)이 되도록 4,000자 남짓으로 채운다.
SOURCE = (
    "Kafka 컨슈머 랙이 1,200건에서 35건으로 줄었다. 처리량은 3.9배. ```\nconsumer.poll(100)\n```"
    + " 본문" * 1300
)


def body(chars: int, extra: str = "") -> str:
    half = chars // 2
    return "## 배경\n" + "가" * half + "\n## 결과\n" + "가" * (chars - half) + extra


def payload(**overrides) -> dict:
    return {
        "error": None,
        "post_type": "case",
        "difficulty": "intermediate",
        "tldr": {"one_liner": "랙을 줄인 사례입니다.", "points": ["a", "b", "c", "d"]},
        "body_md": body(1500, " 랙은 1,200건에서 35건으로 줄었습니다."),
        "glossary": [{"term": "컨슈머 랙", "original": "consumer lag", "explanation": "밀린 양"}],
        "categories": ["streaming"],
        "tags": ["Kafka"],
        **overrides,
    }


class FakeLlm:
    MODELS = ("gemini-3-flash-preview", "nvidia/nemotron:free")

    def __init__(self, *replies: dict) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.users: list[str] = []
        self.candidate_lists: list[list[str] | None] = []

    async def candidates(self, purpose):
        return list(self.MODELS)

    async def complete_json(self, purpose, system, user, *, candidates=None, **kwargs):
        self.calls += 1
        self.users.append(user)
        self.candidate_lists.append(candidates)
        return self.replies.pop(0), (candidates or self.MODELS)[0]


# ── 분량 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("source", "target"),
    [(200, 300), (848, 700), (1000, 800), (3300, 1500), (9400, 3600), (63000, 8000)],
)
def test_the_target_length_follows_the_source(source: int, target: int) -> None:
    """긴 글은 더 길게(최대 8,000자). 짧은 글은 원문의 80%를 넘지 않는다."""
    assert target_chars(source) == target


def test_reading_time_is_at_least_a_minute() -> None:
    assert reading_minutes("가" * 100) == 1
    assert reading_minutes("가" * 2600) == 5


def test_the_prompt_forbids_translation() -> None:
    assert "NOT a translation" in SYSTEM_PROMPT


# ── 코드 검사 ───────────────────────────────────────────────────────
def test_numbers_must_come_from_the_source() -> None:
    ok = check("랙은 1,200건에서 35건으로, 처리량 3.9배" + "가" * 1500, SOURCE, 1500)
    bad = check("랙은 1,500건에서 35건으로" + "가" * 1500, SOURCE, 1500)

    assert ok.numbers_missing == []
    assert bad.numbers_missing == ["1500"]


@pytest.mark.parametrize(
    ("source", "written"),
    [
        ("a 30B-parameter model", "300억 개 파라미터"),
        ("a 4.5 billion token mix", "45억 토큰"),
        ("across ~5k repositories", "약 5,000개 저장소"),
        ("over 70k tasks", "7만 개 이상의 과제"),
        ("1.2M requests", "120만 건"),
    ],
)
def test_unit_conversions_are_not_invented_numbers(source: str, written: str) -> None:
    assert check(written + "가" * 1500, source, 1500).numbers_missing == []


def test_a_single_digit_with_a_unit_is_checked() -> None:
    """2026-10-03 파일럿: "1,000RPM 제한"을 "1RPM 제한"으로 옮긴 해설이 있었다."""
    source = "G마켓은 1,000RPM 연동 수 제한이 있다. 3가지 원인이 있었다." + SOURCE

    assert check("G마켓의 1RPM 제한" + "가" * 1500, source, 1500).numbers_missing == ["1"]
    assert check("3가지 원인과 1,000RPM 제한" + "가" * 1500, source, 1500).numbers_missing == []


def test_invented_scores_are_caught() -> None:
    """2026-10-03 시험: 원문에 없는 경쟁 모델 점수를 지어낸 모델이 있었다."""
    source = "North Mini Code achieves a score of 33.4, outperforming Qwen3.5 (35B-A3B)"
    written = "33.4점으로 Qwen3.5(35B-A3B, 35.4)를 앞섰습니다." + "가" * 1500

    assert check(written, source, 1500).numbers_missing == ["35.4"]


def test_quotes_are_capped() -> None:
    text = "> " + "인용" * 200 + "\n" + "가" * 1000

    assert check(text, SOURCE, 1500).quote_ok is False


def test_code_must_be_copied_from_the_source() -> None:
    good = "가" * 1500 + "\n```python\nconsumer.poll(100)\n```"
    made_up = "가" * 1500 + "\n```python\nconsumer.poll(999)\n```"

    assert check(good, SOURCE, 1500).code_ok is True
    assert check(made_up, SOURCE, 1500).code_ok is False


def test_length_is_checked_against_the_target() -> None:
    assert check("가" * 100, SOURCE, 1500).length_ok is False
    assert check("가" * 1500, SOURCE, 1500).length_ok is True


# ── 생성 ────────────────────────────────────────────────────────────
async def test_a_passing_answer_is_used_once() -> None:
    llm = FakeLlm(payload())

    out = await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]

    assert llm.calls == 1
    assert out.checks.passed
    assert out.tldr.points == ["a", "b", "c"]
    assert out.categories == ["메시징·스트리밍"]
    assert out.generation.generator == "gemini"


async def test_a_failing_answer_is_regenerated_once() -> None:
    wrong = payload(body_md=body(1500, " 랙은 9,999건이었습니다."))
    llm = FakeLlm(wrong, payload())

    out = await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]

    assert llm.calls == 2
    assert out.checks.passed


async def test_the_retry_tells_the_model_what_was_wrong() -> None:
    """모델이 무엇이든 같은 기준으로 고치게 한다 — 짧았으면 몇 자가 필요한지 알려 준다."""
    short = payload(body_md=body(600))
    llm = FakeLlm(short, payload())

    await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]

    assert "previous answer" not in llm.users[0]
    assert "at least 1275" in llm.users[1]


async def test_a_model_that_fails_twice_hands_over_to_the_next() -> None:
    """같은 모델이 피드백을 받고도 지어낸 숫자를 쓰면, 다른 모델에게 맡긴다."""
    wrong = payload(body_md=body(1500, " 9,999건"))
    llm = FakeLlm(wrong, wrong, payload())

    out = await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]

    assert llm.candidate_lists == [None, None, ["nvidia/nemotron:free"]]
    assert out.checks.passed
    assert out.generation.model == "nvidia/nemotron:free"


async def test_three_failures_keep_the_answer_with_its_checks() -> None:
    wrong = payload(body_md=body(1500, " 9,999건"))
    llm = FakeLlm(wrong, wrong, wrong)

    out = await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]

    assert out.checks.numbers_missing == ["9999"]


async def test_an_unreadable_page_is_permanent() -> None:
    llm = FakeLlm(payload(error="봇 차단 페이지"))

    with pytest.raises(PermanentError):
        await ExplainerGenerator(llm).generate("6a0000000000000000000001", "t", "b", SOURCE)  # type: ignore[arg-type]


# ── 요약 잡 연결 ────────────────────────────────────────────────────
class FakePosts:
    async def get_plain_text(self, post_id):
        return SOURCE


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list = []

    async def enqueue(self, job_type, key, payload=None, **kwargs):
        self.jobs.append((job_type, payload))


async def test_the_summary_job_stores_the_explainer_and_its_one_liner() -> None:
    """TL;DR 한 문장이 기존 요약 자리에 들어가 카드·검색·챗봇이 그대로 쓴다."""
    queue = FakeQueue()
    ref = PostRefPayload(post_id="6a0000000000000000000001", title="t", link="l", blog_name="b")
    handler = SummaryRequestedHandler(
        FakePosts(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
        ExplainerGenerator(FakeLlm(payload())),  # type: ignore[arg-type]
    )

    await handler(Job(type=JobType.SUMMARY_REQUESTED, key=ref.post_id, payload=ref.to_dict()))

    [(job_type, sent)] = queue.jobs
    assert job_type == JobType.SUMMARY_COMPLETED
    assert sent["summary"] == "랙을 줄인 사례입니다."
    stored = Explainer.model_validate(sent["explainer"])
    assert str(stored.post_id) == ref.post_id
    assert stored.body_md.startswith("## 배경")


# ── 모델 버릇 ───────────────────────────────────────────────────────
def test_an_english_body_fails() -> None:
    english = "## Intro\n" + "word " * 400 + "\n## More\n" + "word " * 400

    assert check(english, SOURCE, 1500).korean_ok is False


def test_a_summary_without_sections_fails() -> None:
    assert check("가" * 6000, SOURCE, 6900).sections_ok is False
    assert check(
        body(6000).replace("## 결과", "## 결과\n## 한계\n## 방법\n## 배포"), SOURCE, 6900
    ).sections_ok


def test_the_one_liner_must_be_polite() -> None:
    assert check(body(1500), SOURCE, 1500, "줄였습니다.").style_ok
    assert check(body(1500), SOURCE, 1500, "줄였다.").style_ok is False


def test_empty_blockquotes_are_removed() -> None:
    assert clean_body("## 배경\n>\n> \n본문") == "## 배경\n본문"


def test_feedback_names_every_failure() -> None:
    checks = check("word " * 100, SOURCE, 1500, "줄였다.")
    note = feedback(checks, "word " * 100, 1500)

    assert "at least 1275" in note
    assert "Korean" in note
    assert "합니다체" in note
    assert "sections" in note
    assert feedback(check(body(1500), SOURCE, 1500), body(1500), 1500) == ""


def test_copied_paragraphs_fail_even_without_blockquotes() -> None:
    """2026-10-03 파일럿: ">" 없이 원문 문단을 큰따옴표로 옮긴 해설이 있었다."""
    line = "우리는 배치 작업이 새벽마다 멈추는 원인을 추적했고 결국 메모리 부족이 원인이었다. "
    source = line * 3 + SOURCE
    copied = body(300, ' "' + line * 3 + '"')
    own = body(300, " 새벽 배치가 멈춘 원인은 메모리 부족이었습니다.")

    assert check(copied, source, 1500).copy_ok is False
    assert check(own, source, 1500).copy_ok


def test_other_scripts_leaking_into_korean_fail() -> None:
    leaked = body(1500, " このバッチは止まりました. Память")

    assert check(leaked, SOURCE, 1500).korean_ok is False


def test_hanja_from_the_source_is_allowed() -> None:
    source = "AI 번역의 시대, 세태(世態)를 본다." + SOURCE

    assert check(body(1500, " 세태(世態)"), source, 1500).korean_ok
