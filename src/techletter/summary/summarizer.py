"""요약 생성.

**길이·개수 제약은 프롬프트로 지켜지지 않는다.** 무료 모델 11개 중
200자(±20) 요구를 지킨 모델은 하나뿐이었다. 그래서 제약은 프롬프트로
"요청"하되 최종 보장은 코드가 한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.core.errors import PermanentError
from techletter.core.llm.chat import DEFAULT_MAX_TOKENS
from techletter.core.llm.router import truncate_for_model
from techletter.core.logging import get_logger
from techletter.summary.topics import normalize_topics, topic_prompt_lines

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.budget import DailyBudget
    from techletter.core.llm.chat import LlmGateway
    from techletter.settings import SummarySettings

__all__ = [
    "TOPIC_CLASSIFY_INSTRUCTION",
    "Summarizer",
    "SummaryResult",
    "clip_to_sentence",
    "normalize_tags",
]

logger = get_logger(__name__)

_SENTENCE_END = re.compile(r"[.!?。]|다\.|요\.")

_TOPICS = "\n".join(f"   {line}" for line in topic_prompt_lines().splitlines())

SYSTEM_INSTRUCTION = f"""\
You are a content summarization assistant for technical blog posts.
Analyze the provided text and produce a structured summary.
Respond with a valid JSON object containing exactly these four keys:

1. "summary": A concise Korean summary written from a technical perspective.
   Use only technical terms that appear in the original post; add no new information.
   Pick 1-2 main technical points; do not expand into step-by-step implementation
   details or extra optimizations. Keep a polite tone and aim for about 200 characters.
   End by briefly suggesting what a reader can observe from the post, without
   asserting it as a guaranteed benefit.
2. "categories": 1-3 topic slugs chosen ONLY from the list below, most central
   first. Choose by what the post is mainly about, not by technologies mentioned
   in passing. Add a second or third topic only when a substantial part of the post
   is about it (e.g. an AI-based fraud detector -> the AI topic and "security";
   a team onboarding retrospective -> "culture" and the team's field).
   Topics (slug | name | definition):
{_TOPICS}
3. "tags": 3-5 concrete English keywords naming technologies, libraries, frameworks,
   tools, languages, or protocols explicitly mentioned in the text
   (e.g. "Hadoop", "React", "Kubernetes"). No generic concepts, no long phrases,
   no duplicates.
4. "error": null normally. If the text is a bot-verification page, an HTTP error
   page, or is otherwise not a readable article, set a short Korean description
   and leave "summary" empty with empty arrays for the other fields.

Only "summary" is Korean; everything else is English.
Return the raw JSON object with no markdown code fences and no commentary.
"""


@dataclass(slots=True)
class SummaryResult:
    summary: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    model_name: str = ""
    truncated_input: bool = False


def clip_to_sentence(text: str, target: int, tolerance: int) -> str:
    """문장 경계에서 자른다.

    글자 수로만 자르면 문장 중간이 끊겨 어색하다. 목표+허용치를 넘으면
    그 안쪽의 **마지막 문장 끝**까지만 남긴다.
    """
    cleaned = " ".join((text or "").split())
    limit = target + tolerance
    if len(cleaned) <= limit:
        return cleaned

    window = cleaned[:limit]
    ends = [match.end() for match in _SENTENCE_END.finditer(window)]
    # 너무 짧게 잘리면(목표의 절반 미만) 차라리 글자 수로 자른다.
    if ends and ends[-1] >= target - tolerance:
        return window[: ends[-1]].strip()
    return window.rstrip() + "…"


# 이미 요약된 글의 주제만 다시 매긴다. 본문 대신 제목·요약·키워드를 넣어
# 한 번에 여러 건을 보낸다(1,900건을 한 건씩 부르면 무료 한도로 며칠 걸린다).
TOPIC_CLASSIFY_INSTRUCTION = f"""\
You classify tech blog posts into topics.
Input is a JSON array of posts with id, title, blog, summary and keywords.
Return ONLY a JSON object: {{"results": [{{"id": "...", "topics": ["slug", ...]}}]}}
with one entry per input post.
Pick 1-3 topic slugs per post from the list below, most central first.
Choose by what the post is mainly about, not by technologies mentioned in passing.
Add a second or third topic only when a substantial part of the post is about it
(e.g. an AI-based fraud detector -> the AI topic and "security"; a team onboarding
retrospective -> "culture" and the team's field). Use "other" only when nothing fits.

Topics (slug | name | definition):
{topic_prompt_lines()}
"""
# 추론 토큰을 쓰는 모델이 결과를 쓰기도 전에 한도를 다 쓰지 않게 넉넉히 준다.
_CLASSIFY_MAX_TOKENS = 8000


def normalize_tags(values: Any, limit: int) -> list[str]:
    """중복(대소문자 무시)을 없애고 개수를 자른다."""
    if not isinstance(values, list):
        return []
    kept: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip()
        key = tag.lower()
        if not tag or key in seen or len(tag) > 40:
            continue
        seen.add(key)
        kept.append(tag)
        if len(kept) >= limit:
            break
    return kept


class Summarizer:
    """요약 한 건.

    `budget`과 `primary_model`을 주면 **1순위 모델을 예산 안에서만** 쓴다.
    Gemini 무료 티어는 하루 20회라, 다 쓰고 나서 429를 맞고 재시도하는
    대신 미리 무료 모델로 흘린다.
    """

    def __init__(
        self,
        llm: LlmGateway,
        settings: SummarySettings,
        *,
        budget: DailyBudget | None = None,
        primary_model: str = "",
        primary_provider: str = "google",
        daily_limit: int = 0,
    ) -> None:
        self._llm = llm
        self._settings = settings
        self._budget = budget
        self._primary_model = primary_model
        self._primary_provider = primary_provider
        self._daily_limit = daily_limit

    async def _candidates(self) -> list[str] | None:
        """예산이 남았으면 1순위 모델을 맨 앞에 세우고, 그 자리에서 예산을 센다.

        맨 앞에 선 모델은 반드시 한 번 호출된다. 실패한 호출도 구글 한도를 깎으므로
        성공했을 때만 세면 장부가 실제 사용량보다 적게 나와 한도를 넘긴다.
        """
        if not (self._budget and self._primary_model):
            return None
        if not await self._budget.has_room(self._primary_provider, self._daily_limit):
            logger.info(
                "primary model budget exhausted; falling back",
                extra={"provider": self._primary_provider},
            )
            return None
        await self._budget.consume(self._primary_provider)
        fallback = await self._llm.candidates("summary")
        return [self._primary_model, *(m for m in fallback if m != self._primary_model)]

    async def summarize(self, plain_text: str) -> SummaryResult:
        # 본문 최대가 91K자다. 그대로 넣으면 무료 모델의 컨텍스트를 넘고
        # 비용·지연도 입력에 비례한다.
        text, truncated = truncate_for_model(plain_text, self._settings.max_input_chars)

        payload, model_id = await self._llm.complete_json(
            "summary",
            SYSTEM_INSTRUCTION,
            text,
            max_tokens=DEFAULT_MAX_TOKENS,
            candidates=await self._candidates(),
        )

        error = payload.get("error")
        if error:
            # 모델이 "요약할 수 없는 내용"이라고 판단했다. 다시 불러도 같다.
            raise PermanentError(
                f"model judged the content unsummarizable: {str(error)[:200]}",
                reason="not_summarizable",
            )

        summary = clip_to_sentence(
            str(payload.get("summary") or ""),
            self._settings.summary_target_chars,
            self._settings.summary_tolerance_chars,
        )
        if not summary:
            # `error`가 비어 있어도 요약이 없으면 실패다.
            raise PermanentError("model returned an empty summary", reason="empty_summary")

        return SummaryResult(
            summary=summary,
            categories=normalize_topics(payload.get("categories")),
            tags=normalize_tags(payload.get("tags"), self._settings.max_tags),
            model_name=model_id,
            truncated_input=truncated,
        )

    async def classify_topics(self, posts: list[dict[str, Any]]) -> dict[str, list[str]]:
        """`{id, title, blog, summary, keywords}` 목록 → id별 주제 이름.

        모델이 빠뜨린 글은 결과에 없다. 호출한 쪽이 다음에 다시 시도한다.
        """
        payload, model_id = await self._llm.complete_json(
            "summary",
            TOPIC_CLASSIFY_INSTRUCTION,
            json.dumps(posts, ensure_ascii=False),
            max_tokens=_CLASSIFY_MAX_TOKENS,
            candidates=await self._candidates(),
        )
        wanted = {str(post["id"]) for post in posts}
        results: dict[str, list[str]] = {}
        for row in payload.get("results") or []:
            if not isinstance(row, dict):
                continue
            post_id = str(row.get("id") or "")
            if post_id in wanted:
                results[post_id] = normalize_topics(row.get("topics"))
        logger.info(
            "topics classified",
            extra={"model": model_id, "asked": len(posts), "answered": len(results)},
        )
        return results
