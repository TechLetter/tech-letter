"""답변 생성.

목록 요청은 **LLM을 부르지 않는다**. 제목·링크·발행일을 나열하는 데 모델이
필요 없고, 모델을 쓰면 링크를 지어내거나 개수를 틀린다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from techletter.chat.agent.prompts import (
    ANSWER_SYSTEM_PROMPT,
    BRIEF_ANSWER_SYSTEM_PROMPT,
    NO_MATCH_ANSWER,
)
from techletter.chat.agent.state import PostRecord, ToolResult

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.memory import Turn
    from techletter.core.llm.chat import LlmGateway

__all__ = [
    "NO_RESULT_MESSAGE",
    "AnswerGeneration",
    "AnswerGenerator",
    "build_post_context",
    "format_post_list",
]

NO_RESULT_MESSAGE = "요청 조건에 맞는 포스트를 찾지 못했습니다."
SUMMARY_PREVIEW_CHARS = 160
MAX_LABELS = 5
AnswerGeneration = tuple[str, str | None]
# 이전 답은 길다. 무엇을 이어 묻는지 알 만큼만 넣는다 — 사실의 근거는 이번에 읽은 글이다.
_HISTORY_TURN_CHARS = 600


def build_post_context(posts: list[PostRecord], *, summaries_only: bool = False) -> str:
    """선택된 포스트를 프롬프트용 텍스트로 만든다.

    `summaries_only`면 본문 대신 요약본만 넣는다 — 검색 AI 요약은 짧게 답하니
    본문 여러 편이 컨텍스트 상한에 걸려 뒤쪽 글이 잘리는 것보다 요약 전부가 낫다.
    """
    blocks: list[str] = []
    for index, post in enumerate(posts, 1):
        blocks.append(
            "\n".join(
                [
                    f"[Post {index}]",
                    f"Title: {post.title}",
                    f"Blog: {post.blog_name}",
                    f"Published At: {post.published_at}",
                    f"Link: {post.link}",
                    'Content: """',
                    (post.summary if summaries_only else post.plain_text or post.summary)
                    or "본문/요약 없음",
                    '"""',
                ]
            )
        )
    return "\n\n".join(blocks)


def format_post_list(result: ToolResult) -> str:
    if not result.posts:
        return result.message or NO_RESULT_MESSAGE

    header = (
        f"{result.message or '조건에 맞는 포스트를 조회했습니다.'} "
        f"전체 {result.total}개 중 {len(result.posts)}개입니다."
    )
    lines: list[str] = [header, ""]
    for index, post in enumerate(result.posts, 1):
        published = post.published_at[:10] if post.published_at else "발행일 없음"
        lines.append(f"{index}. [{post.title}]({post.link}) - {post.blog_name} ({published})")
        if post.summary:
            lines.append(f"   - {post.summary[:SUMMARY_PREVIEW_CHARS]}")
        labels = post.tags or post.categories
        if labels:
            lines.append(f"   - 태그: {', '.join(labels[:MAX_LABELS])}")
        lines.append("")
    return "\n".join(lines).strip()


# 일부 무료 모델이 [1] 대신 전각 괄호 【1】·［1］을 쓴다(2026-10-03 채점에서 74건 중 10건).
_WIDE_CITATION = re.compile(r"[【［]\s*(\d{1,2})\s*[】］]")


def _normalize_citations(text: str) -> str:
    return _WIDE_CITATION.sub(r"[\1]", text)


class AnswerGenerator:
    def __init__(self, llm: LlmGateway, *, max_context_chars: int = 24000) -> None:
        self._llm = llm
        self._max_context_chars = max_context_chars

    async def answer(
        self,
        query: str,
        result: ToolResult,
        recent: list[Turn],
        model_id: str | None = None,
    ) -> AnswerGeneration:
        """번호 붙은 글로 답한다. 글이 질문과 무관하면 `NO_MATCH_ANSWER`를 준다."""
        history = "\n".join(f"{turn.role}: {turn.content[:_HISTORY_TURN_CHARS]}" for turn in recent)
        parts = [
            f"[이전 대화]\n{history}" if history else "",
            f"[글]\n{result.context[: self._max_context_chars]}",
            f"[질문]\n{query}",
        ]
        return await self._complete(
            ANSWER_SYSTEM_PROMPT, "\n\n".join(p for p in parts if p), model_id
        )

    async def brief(self, query: str, result: ToolResult) -> AnswerGeneration:
        """검색 결과 AI 요약. 요약본만 읽고 짧게 쓴다."""
        payload = f"[Search]\n{query}\n\n[Posts]\n{result.context[: self._max_context_chars]}"
        return await self._complete(BRIEF_ANSWER_SYSTEM_PROMPT, payload, None)

    async def _complete(self, system: str, user: str, model_id: str | None) -> AnswerGeneration:
        candidates: list[str] | None = None
        if model_id is not None:
            automatic = await self._llm.candidates("chat")
            # 사용자의 선택만 앞에 넣고 중복을 없앤다. 명시 후보는 라우터가 다시 자르지
            # 않으니 시도 상한을 여기서 건다.
            router = getattr(self._llm, "_router", None)
            settings = getattr(router, "_settings", None)
            max_attempts = getattr(settings, "max_model_attempts", 3)
            max_attempts = max(max_attempts if isinstance(max_attempts, int) else 3, 1)
            candidates = list(dict.fromkeys([model_id, *automatic]))[:max_attempts]
        answer, used = await self._llm.complete("chat", system, user, candidates=candidates)
        return _normalize_citations((answer or "").strip()) or NO_MATCH_ANSWER, used
