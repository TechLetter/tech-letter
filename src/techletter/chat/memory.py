"""대화 맥락.

LLM을 부르지 않는다. 최근 대화 몇 턴과 **직전 답의 출처 글 id**만 넘긴다.
예전에는 후속 질문마다 LLM으로 질문을 다시 쓰고, 긴 대화는 워커가 요약했다.
재작성은 모든 후속 질문에 호출 하나를 더했고, "거기서"가 가리키는 글은 출처 id가
더 정확히 알려 준다(`chat/agent/scope.py::is_reference`).

대화 기록은 **신뢰할 수 없는 입력**이다. 프롬프트에는 참고 자료로만 넣는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.models import ChatMessage
    from techletter.settings import ChatSettings

__all__ = ["MemoryBuilder", "MemoryContext", "Turn"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Turn:
    role: str
    content: str


@dataclass(slots=True)
class MemoryContext:
    recent: list[Turn] = field(default_factory=list)
    previous_query: str = ""
    """직전 사용자 질문. 짧은 후속 질문의 검색어를 보강한다."""
    previous_source_ids: list[str] = field(default_factory=list)
    """직전 답의 출처 글. "거기서", "그 글"이 가리키는 범위다."""
    history_message_count: int = 0

    @property
    def used(self) -> bool:
        return bool(self.recent)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "used": self.used,
            "strategy": "recent_window" if self.used else "none",
            "recent_message_count": len(self.recent),
            "history_message_count": self.history_message_count,
            "status": "ready" if self.used else "none",
        }


class MemoryBuilder:
    def __init__(self, settings: ChatSettings) -> None:
        self._settings = settings

    def _clean(self, messages: list[ChatMessage]) -> list[Turn]:
        turns: list[Turn] = []
        for message in messages:
            if message.role not in {"user", "assistant"}:
                continue
            content = message.content.strip()[: self._settings.memory_max_message_chars]
            if content:
                turns.append(Turn(role=message.role, content=content))
        return turns

    async def build(
        self,
        query: str,
        messages: list[ChatMessage],
    ) -> MemoryContext:
        del query  # 질문을 다시 쓰지 않는다
        history = self._clean(messages)
        if not history:
            return MemoryContext()
        previous_query = next((m.content for m in reversed(messages) if m.role == "user"), "")
        last_answer = next((m for m in reversed(messages) if m.role == "assistant"), None)
        sources = ((last_answer.metadata or {}).get("sources") or []) if last_answer else []
        return MemoryContext(
            recent=history[-self._settings.memory_recent_messages :],
            previous_query=previous_query[: self._settings.memory_max_message_chars],
            previous_source_ids=[
                str(s.get("post_id")) for s in sources if isinstance(s, dict) and s.get("post_id")
            ],
            history_message_count=len(history),
        )
