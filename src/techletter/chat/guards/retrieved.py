"""검색 결과 가드.

남의 블로그 본문에 섞인 지시문을 **차단하지 않는다.** 프롬프트 인젝션을
다루는 기술 글이라면 당연히 그런 문장이 들어 있다. 대신 위험 표시를 붙여
프롬프트에서 "신뢰할 수 없는 문서"로 감싼다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from techletter.chat.guards.rules import RETRIEVED_CONTENT_RULES

__all__ = ["RetrievedContentGuard", "RetrievedContentResult"]


@dataclass(frozen=True, slots=True)
class RetrievedContentResult:
    categories: list[str] = field(default_factory=list)

    @property
    def risky(self) -> bool:
        return bool(self.categories)


class RetrievedContentGuard:
    def __init__(self) -> None:
        self._rules = RETRIEVED_CONTENT_RULES

    def inspect(self, text: str) -> RetrievedContentResult:
        return RetrievedContentResult(
            categories=[rule.category for rule in self._rules if rule.pattern.search(text)]
        )
