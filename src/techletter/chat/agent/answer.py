"""답변 생성.

목록 요청은 **LLM을 부르지 않는다**. 제목·링크·발행일을 나열하는 데 모델이
필요 없고, 모델을 쓰면 링크를 지어내거나 개수를 틀린다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from techletter.chat.agent.prompts import ANSWER_SYSTEM_PROMPT
from techletter.chat.agent.state import ChatPlan, PostRecord, ToolResult

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.chat import LlmGateway

__all__ = ["NO_RESULT_MESSAGE", "AnswerGenerator", "build_post_context", "format_post_list"]

NO_RESULT_MESSAGE = "요청 조건에 맞는 포스트를 찾지 못했습니다."
SUMMARY_PREVIEW_CHARS = 160
MAX_LABELS = 5


def build_post_context(posts: list[PostRecord]) -> str:
    """선택된 포스트를 프롬프트용 텍스트로 만든다."""
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
                    post.plain_text or post.summary or "본문/요약 없음",
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


class AnswerGenerator:
    def __init__(self, llm: LlmGateway, *, max_context_chars: int = 24000) -> None:
        self._llm = llm
        self._max_context_chars = max_context_chars

    async def generate(
        self, query: str, plan: ChatPlan, result: ToolResult, memory_metadata: dict[str, object]
    ) -> str:
        if result.status in {"no_result", "failed"}:
            return result.message or NO_RESULT_MESSAGE
        if plan.task == "list_posts":
            return format_post_list(result)

        payload = {
            "query": query,
            "plan": {
                "task": plan.task,
                "strict_scope": plan.strict_scope,
                "needs_content": plan.needs_content,
                "reason": plan.reason,
            },
            "memory": memory_metadata,
            "tool_result": {
                "status": result.status,
                "total": result.total,
                "message": result.message,
                # 무료 모델은 컨텍스트가 작다. 넘치면 뒤를 자른다.
                "context": result.context[: self._max_context_chars],
                "posts": [
                    {
                        "title": post.title,
                        "blog_name": post.blog_name,
                        "link": post.link,
                        "published_at": post.published_at,
                        "summary": post.summary,
                    }
                    for post in result.posts
                ],
            },
        }
        answer, _ = await self._llm.complete(
            "chat", ANSWER_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)
        )
        return answer or NO_RESULT_MESSAGE
