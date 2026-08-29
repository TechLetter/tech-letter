"""질문 → 실행 계획.

계획이 실패해도 대화는 이어져야 한다. 파싱이든 호출이든 실패하면
`general_rag`로 떨어뜨린다 — 벡터 검색은 제약 없이도 동작한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from techletter.chat.agent.policies import DEFAULT_POST_LIMIT, normalize_plan
from techletter.chat.agent.prompts import PLANNER_SYSTEM_PROMPT
from techletter.chat.agent.state import ChatPlan, PostConstraints
from techletter.core.logging import get_logger
from techletter.core.time import ensure_utc

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.chat import LlmGateway

__all__ = ["KST", "VALID_TASKS", "QueryPlanner", "parse_plan"]

logger = get_logger(__name__)

# 사용자의 "지난달", "이번 주"는 한국 시간 기준이다.
KST = ZoneInfo("Asia/Seoul")
VALID_TASKS: frozenset[str] = frozenset(
    {
        "list_posts",
        "summarize_posts",
        "answer_from_posts",
        "semantic_search_posts",
        "general_rag",
        "no_result",
    }
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        # 모델이 "지난달" 같은 문자열을 그대로 넣기도 한다. 제약을 버린다.
        logger.debug("planner returned an unparsable date", extra={"value": text[:60]})
        return None


def _limit(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_POST_LIMIT


def parse_plan(payload: dict[str, Any]) -> ChatPlan:
    task = payload.get("task")
    constraints = payload.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}
    return normalize_plan(
        ChatPlan(
            task=task if isinstance(task, str) and task in VALID_TASKS else "general_rag",  # type: ignore[arg-type]
            constraints=PostConstraints(
                published_from=_datetime(constraints.get("published_from")),
                published_to=_datetime(constraints.get("published_to")),
                blog_name=_text(constraints.get("blog_name")),
                categories=_strings(constraints.get("categories")),
                tags=_strings(constraints.get("tags")),
                limit=_limit(constraints.get("limit")),
            ),
            strict_scope=bool(payload.get("strict_scope")),
            needs_content=bool(payload.get("needs_content")),
            reason=_text(payload.get("reason")) or "",
        )
    )


class QueryPlanner:
    def __init__(self, llm: LlmGateway) -> None:
        self._llm = llm

    async def plan(self, query: str, memory_metadata: dict[str, Any]) -> ChatPlan:
        import json  # noqa: PLC0415

        try:
            payload, _ = await self._llm.complete_json(
                "planner",
                PLANNER_SYSTEM_PROMPT.format(now_iso=datetime.now(KST).isoformat()),
                json.dumps({"query": query, "memory": memory_metadata}, ensure_ascii=False),
                max_tokens=2000,
            )
        except Exception:
            logger.warning("planning failed; falling back to general_rag", exc_info=True)
            return normalize_plan(ChatPlan(task="general_rag", reason="planner_failed"))
        return parse_plan(payload)
