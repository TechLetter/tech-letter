from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ...domain.chat.policies import normalize_plan
from ...domain.chat.schemas import ChatPlan, ChatTask, PostConstraints
from ...services.conversation_memory import ConversationMemoryContext
from .prompts import PLANNER_SYSTEM_PROMPT


logger = logging.getLogger(__name__)

VALID_TASKS: set[str] = {
    "list_posts",
    "summarize_posts",
    "answer_from_posts",
    "semantic_search_posts",
    "general_rag",
    "no_result",
}


class LLMQueryPlanner:
    def __init__(self, llm) -> None:
        self._llm = llm

    def plan(
        self,
        *,
        query: str,
        memory: ConversationMemoryContext,
        now: datetime,
    ) -> ChatPlan:
        try:
            response = self._llm.invoke(
                [
                    SystemMessage(
                        content=PLANNER_SYSTEM_PROMPT.format(
                            now_iso=now.isoformat(),
                        )
                    ),
                    HumanMessage(
                        content=json.dumps(
                            {
                                "query": query,
                                "memory": memory.to_metadata(),
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            return normalize_plan(_parse_plan(str(response.content)))
        except Exception:  # noqa: BLE001
            logger.exception("failed to plan chat query; falling back to general_rag")
            return ChatPlan(task="general_rag", reason="planner_failed")


def _parse_plan(raw_content: str) -> ChatPlan:
    payload = _extract_json(raw_content)
    task = _normalize_task(payload.get("task"))
    constraints_payload = payload.get("constraints")
    if not isinstance(constraints_payload, dict):
        constraints_payload = {}

    constraints = PostConstraints(
        published_from=_parse_datetime(constraints_payload.get("published_from")),
        published_to=_parse_datetime(constraints_payload.get("published_to")),
        blog_name=_optional_string(constraints_payload.get("blog_name")),
        categories=_string_list(constraints_payload.get("categories")),
        tags=_string_list(constraints_payload.get("tags")),
        limit=_parse_limit(constraints_payload.get("limit")),
    )
    return ChatPlan(
        task=task,
        constraints=constraints,
        strict_scope=bool(payload.get("strict_scope")),
        needs_content=bool(payload.get("needs_content")),
        reason=_optional_string(payload.get("reason")) or "",
    )


def _extract_json(raw_content: str) -> dict[str, Any]:
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("planner response must be a JSON object")
    return parsed


def _normalize_task(value: Any) -> ChatTask:
    if isinstance(value, str) and value in VALID_TASKS:
        return value  # type: ignore[return-value]
    return "general_rag"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _parse_limit(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10
