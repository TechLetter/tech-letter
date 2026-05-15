from __future__ import annotations

from datetime import datetime, timezone

from chatbot_service.app.application.chat.ports import ChatInput
from chatbot_service.app.domain.chat.schemas import ChatPlan, PostConstraints, ToolResult
from chatbot_service.app.guards.output_guard import OutputGuard
from chatbot_service.app.guards.prompt_guard import PromptGuard
from chatbot_service.app.infrastructure.graph.langgraph_chat import LangGraphChatWorkflow
from chatbot_service.app.services.conversation_memory import ConversationMemoryContext


class FakeMemoryService:
    def build(self, query, messages, stored_memory):
        return ConversationMemoryContext(
            used=False,
            compressed=False,
            compression_failed=False,
            strategy="none",
            summary="",
            recent_messages=[],
            summary_message_count=0,
            recent_message_count=0,
            history_message_count=0,
            rewritten_query=query,
            rewritten=False,
            status="none",
        )


class FakePlanner:
    def __init__(self, plan: ChatPlan) -> None:
        self._plan = plan

    def plan(self, *, query, memory, now):
        return self._plan


class FakePostQuery:
    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.list_calls = 0
        self.hydrate_calls = 0

    def list_posts(self, constraints):
        self.list_calls += 1
        return self.result

    def hydrate_content(self, posts):
        self.hydrate_calls += 1
        return posts


class FakeSemanticSearch:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query, constraints=None):
        self.calls += 1
        return ToolResult(status="ok", context="semantic", total=1)


class FakeAnswerGenerator:
    def generate(self, *, query, plan, tool_result, memory):
        if tool_result.status == "no_result":
            return tool_result.message
        return "답변"


def test_strict_scoped_post_summary_does_not_fall_back_to_vector_search() -> None:
    post_query = FakePostQuery(
        ToolResult(
            status="no_result",
            message="오늘 조건에 맞는 포스트를 찾지 못했습니다.",
        )
    )
    semantic_search = FakeSemanticSearch()
    workflow = LangGraphChatWorkflow(
        prompt_guard=PromptGuard(),
        output_guard=OutputGuard(),
        memory_service=FakeMemoryService(),
        planner=FakePlanner(
            ChatPlan(
                task="summarize_posts",
                constraints=PostConstraints(
                    published_from=datetime(2026, 5, 14, tzinfo=timezone.utc),
                    limit=10,
                ),
                strict_scope=True,
                needs_content=True,
            )
        ),
        post_query=post_query,
        semantic_search=semantic_search,
        answer_generator=FakeAnswerGenerator(),
    )

    result = workflow.run(ChatInput(query="오늘 하루 포스트 내용 찾아줘", messages=[]))

    assert "찾지 못했습니다" in result.answer
    assert post_query.list_calls == 1
    assert post_query.hydrate_calls == 0
    assert semantic_search.calls == 0
    assert result.agent["intent"] == "summarize_posts"
    assert result.agent["activities"] == [
        {"type": "guard", "label": "질문 안전성 확인", "status": "completed"},
        {"type": "plan", "label": "조회 계획 수립", "status": "completed"},
        {"type": "list_posts", "label": "포스트 목록 조회", "status": "completed"},
        {"type": "answer", "label": "답변 생성", "status": "completed"},
    ]
