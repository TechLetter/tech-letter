from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ...domain.chat.schemas import ChatPlan, ToolResult
from ...services.conversation_memory import ConversationMemoryContext
from .prompts import ANSWER_SYSTEM_PROMPT


class LLMAnswerGenerator:
    def __init__(self, llm) -> None:
        self._llm = llm

    def generate(
        self,
        *,
        query: str,
        plan: ChatPlan,
        tool_result: ToolResult,
        memory: ConversationMemoryContext,
    ) -> str:
        if tool_result.status == "no_result":
            return tool_result.message or "요청 조건에 맞는 포스트를 찾지 못했습니다."

        if plan.task == "list_posts":
            return _format_post_list_answer(plan, tool_result)

        response = self._llm.invoke(
            [
                SystemMessage(content=ANSWER_SYSTEM_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "query": query,
                            "plan": {
                                "task": plan.task,
                                "strict_scope": plan.strict_scope,
                                "needs_content": plan.needs_content,
                                "reason": plan.reason,
                            },
                            "memory": memory.to_metadata(),
                            "tool_result": {
                                "status": tool_result.status,
                                "total": tool_result.total,
                                "message": tool_result.message,
                                "context": tool_result.context,
                                "posts": [
                                    {
                                        "title": post.title,
                                        "blog_name": post.blog_name,
                                        "link": post.link,
                                        "published_at": post.published_at,
                                        "summary": post.summary,
                                        "plain_text": post.plain_text,
                                    }
                                    for post in tool_result.posts
                                ],
                            },
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        return str(response.content).strip()


def _format_post_list_answer(plan: ChatPlan, tool_result: ToolResult) -> str:
    if not tool_result.posts:
        return tool_result.message or "요청 조건에 맞는 포스트를 찾지 못했습니다."

    lines = [
        f"{tool_result.message or '조건에 맞는 포스트를 조회했습니다.'} "
        f"전체 {tool_result.total}개 중 {len(tool_result.posts)}개입니다.",
        "",
    ]
    for index, post in enumerate(tool_result.posts, 1):
        lines.append(
            f"{index}. [{post.title}]({post.link}) - {post.blog_name}"
            f" ({post.published_at[:10] if post.published_at else '발행일 없음'})"
        )
        if post.summary:
            lines.append(f"   - {post.summary[:160]}")
        labels = post.tags or post.categories
        if labels:
            lines.append(f"   - 태그: {', '.join(labels[:5])}")
        lines.append("")
    return "\n".join(lines).strip()
