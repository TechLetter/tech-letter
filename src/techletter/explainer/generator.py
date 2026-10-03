"""쉽게 읽기 생성 — 한 번의 호출로 JSON을 받고, 코드 검사에 걸리면 고쳐 쓰게 한다.

모델마다 버릇이 달라(짧게 줄이는 모델, 반말로 끝내는 모델, 원문에 없는 점수를 지어내는
모델) 프롬프트만으로는 고르게 나오지 않는다. 그래서 어느 모델이든 같은 코드 검사를 거친다.

1. 체인 순서대로 한 번 부른다.
2. 검사에 걸리면 무엇이 모자랐는지(분량·섹션·언어·문체·숫자)를 덧붙여 다시 부른다.
3. 또 걸리면 이미 실패한 모델을 빼고 다음 모델에게 같은 피드백으로 맡긴다.

모델 순서와 한도는 요약 워커의 `LlmGateway`를 그대로 쓴다(3 Flash → 3.5 Flash Lite → 무료 모델).
두 번째도 검사에 걸리면 결과를 버리지 않고 검사 결과와 함께 저장한다(관리자가 본다).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger
from techletter.explainer.checks import check, clean_body, feedback
from techletter.explainer.models import Explainer, Generation, GlossaryItem, Tldr
from techletter.explainer.prompt import PROMPT_VERSION, SYSTEM_PROMPT, target_chars, user_message
from techletter.summary.topics import normalize_tags, normalize_topics

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.chat import LlmGateway

__all__ = ["ExplainerGenerator", "explainer_from_payload", "reading_minutes"]

logger = get_logger(__name__)

MAX_INPUT_CHARS = 70000
"""원문 최대가 약 63,000자다. Gemini는 입력 100만 토큰이라 통째로 넣는다."""
MAX_OUTPUT_TOKENS = 16000
MAX_ATTEMPTS = 3
KOREAN_CHARS_PER_MINUTE = 500
_POST_TYPES = {"research", "case", "tutorial", "news"}
_DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def reading_minutes(body_md: str) -> int:
    return max(1, round(len(body_md) / KOREAN_CHARS_PER_MINUTE))


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def explainer_from_payload(
    post_id: str, payload: dict[str, Any], source: str, *, generation: Generation
) -> Explainer:
    """모델이 준 JSON(또는 백필 파일) → 저장할 문서. 값을 정리하고 검사한다."""
    tldr = payload.get("tldr") or {}
    body = clean_body(str(payload.get("body_md") or ""))
    points = [str(p).strip() for p in (tldr.get("points") or []) if str(p).strip()][:3]
    glossary = [
        GlossaryItem(
            term=str(g.get("term") or "").strip(),
            original=str(g.get("original") or "").strip(),
            explanation=str(g.get("explanation") or "").strip(),
        )
        for g in (payload.get("glossary") or [])
        if isinstance(g, dict) and str(g.get("term") or "").strip()
    ][:8]
    post_type = str(payload.get("post_type") or "case")
    difficulty = str(payload.get("difficulty") or "intermediate")
    one_liner = str(tldr.get("one_liner") or "").strip()
    return Explainer(
        post_id=post_id,  # type: ignore[arg-type]
        post_type=post_type if post_type in _POST_TYPES else "case",  # type: ignore[arg-type]
        difficulty=difficulty if difficulty in _DIFFICULTIES else "intermediate",  # type: ignore[arg-type]
        reading_minutes=reading_minutes(body),
        tldr=Tldr(one_liner=one_liner, points=points),
        body_md=body,
        glossary=glossary,
        categories=normalize_topics(payload.get("categories")),
        tags=normalize_tags(payload.get("tags"), 5),
        checks=check(body, source, target_chars(len(source)), one_liner),
        generation=generation,
    )


class ExplainerGenerator:
    def __init__(self, llm: LlmGateway) -> None:
        self._llm = llm

    async def generate(self, post_id: str, title: str, blog_name: str, text: str) -> Explainer:
        source = text[:MAX_INPUT_CHARS]
        target = target_chars(len(source))
        user = user_message(title, blog_name, source, target)
        best: Explainer | None = None
        failed: list[str] = []
        prompt = user
        for attempt in range(MAX_ATTEMPTS):
            candidates = None
            if attempt == MAX_ATTEMPTS - 1:
                candidates = [m for m in await self._llm.candidates("summary") if m not in failed]
                if not candidates:
                    break
            payload, model_id = await self._llm.complete_json(
                "summary",
                SYSTEM_PROMPT,
                prompt,
                max_tokens=MAX_OUTPUT_TOKENS,
                candidates=candidates,
            )
            if payload.get("error"):
                # 모델이 "읽을 수 있는 글이 아니다"라고 판단했다. 다시 불러도 같다.
                raise PermanentError(
                    f"model judged the content unreadable: {str(payload['error'])[:200]}",
                    reason="not_summarizable",
                )
            explainer = explainer_from_payload(
                post_id,
                payload,
                source,
                generation=Generation(
                    generator="gemini" if model_id.startswith("gemini") else "openrouter",
                    model=model_id,
                    prompt_version=PROMPT_VERSION,
                    source_chars=len(source),
                    source_hash=source_hash(source),
                ),
            )
            if not explainer.tldr.one_liner or not explainer.body_md:
                raise PermanentError("model returned an empty explainer", reason="empty_summary")
            if explainer.checks.passed:
                return explainer
            logger.info(
                "explainer failed checks",
                extra={
                    "post_id": post_id,
                    "attempt": attempt,
                    "model_id": model_id,
                    "checks": explainer.checks.to_mongo(),
                },
            )
            failed.append(model_id)
            if best is None or _score(explainer) > _score(best):
                best = explainer
            prompt = (
                f"{user}\n\nYour previous answer did not meet these requirements. Write the "
                f"whole JSON again and fix them:\n"
                f"{feedback(explainer.checks, explainer.body_md, target)}"
            )
        assert best is not None
        return best


def _score(explainer: Explainer) -> tuple[int, int]:
    """끝내 검사에 걸리면 덜 걸린 쪽, 같으면 긴 쪽을 남긴다."""
    c = explainer.checks
    flags = [c.length_ok, c.quote_ok, c.code_ok, not c.numbers_missing, c.korean_ok]
    flags += [c.sections_ok, c.style_ok]
    return sum(flags), len(explainer.body_md)
