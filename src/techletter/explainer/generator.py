"""쉽게 읽기 생성 — 한 번의 호출로 JSON을 받는다.

모델 순서와 한도는 `LlmGateway`가 정한다(3 Flash → 3.5 Flash Lite → 무료 모델). API 오류·한도
초과일 때만 다음 모델로 넘어간다.

코드 검사(`checks.py`)는 결과에 기록만 하고 재시도하지 않는다(2026-10-04 사용자 결정). 검사에
걸려 다시 부르면 약한 무료 모델로 넘어가 오히려 사실 오류가 났다(v5 파일럿). 품질은 기록된
검사 결과와 별도 평가로 나중에 본다.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from techletter.core.errors import PermanentError
from techletter.core.logging import get_logger
from techletter.explainer.checks import check, clean_body
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
    all_points = [str(p).strip() for p in (tldr.get("points") or []) if str(p).strip()]
    points = all_points[:3]
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
        checks=check(body, source, target_chars(len(source)), one_liner, len(all_points)),
        generation=generation,
    )


class ExplainerGenerator:
    def __init__(self, llm: LlmGateway) -> None:
        self._llm = llm

    async def generate(self, post_id: str, title: str, blog_name: str, text: str) -> Explainer:
        source = text[:MAX_INPUT_CHARS]
        target = target_chars(len(source))
        user = user_message(title, blog_name, source, target)
        payload, model_id = await self._llm.complete_json(
            "summary", SYSTEM_PROMPT, user, max_tokens=MAX_OUTPUT_TOKENS
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
        if not explainer.checks.passed:
            logger.info(
                "explainer failed checks",
                extra={
                    "post_id": post_id,
                    "model_id": model_id,
                    "checks": explainer.checks.to_mongo(),
                },
            )
        return explainer
