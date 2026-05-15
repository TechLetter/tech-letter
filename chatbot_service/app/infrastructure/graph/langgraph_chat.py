from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from ...application.chat.ports import (
    AnswerGeneratorPort,
    ChatInput,
    PostQueryPort,
    QueryPlannerPort,
    SemanticSearchPort,
)
from ...domain.chat.policies import normalize_plan, should_return_no_result
from ...domain.chat.schemas import ChatPlan, ChatResult, PostRecord, ToolResult
from ...guards.output_guard import OutputGuard
from ...guards.prompt_guard import PromptGuard
from ...guards.schemas import PolicyViolationError
from ...services.conversation_memory import (
    ConversationMemoryContext,
    ConversationMemoryService,
)


KST = ZoneInfo("Asia/Seoul")


class ChatGraphState(TypedDict, total=False):
    query: str
    safe_query: str
    search_query: str
    messages: list
    stored_memory: object
    on_activity: object
    activities: list[dict[str, str]]
    guard: dict[str, Any]
    memory_context: ConversationMemoryContext
    memory: dict[str, Any]
    plan: ChatPlan
    tool_result: ToolResult
    answer: str
    sources: list[dict[str, Any]]


class LangGraphChatWorkflow:
    def __init__(
        self,
        *,
        prompt_guard: PromptGuard,
        output_guard: OutputGuard,
        memory_service: ConversationMemoryService,
        planner: QueryPlannerPort,
        post_query: PostQueryPort,
        semantic_search: SemanticSearchPort,
        answer_generator: AnswerGeneratorPort,
    ) -> None:
        self._prompt_guard = prompt_guard
        self._output_guard = output_guard
        self._memory_service = memory_service
        self._planner = planner
        self._post_query = post_query
        self._semantic_search = semantic_search
        self._answer_generator = answer_generator
        self._graph = self._build_graph()

    def run(self, chat_input: ChatInput) -> ChatResult:
        initial_state: ChatGraphState = {
            "query": chat_input.query,
            "messages": chat_input.messages,
            "stored_memory": chat_input.stored_memory,
            "on_activity": chat_input.on_activity,
            "activities": [],
        }
        state = self._graph.invoke(initial_state)
        return ChatResult(
            answer=state["answer"],
            sources=state.get("sources", []),
            agent={
                "mode": "agent",
                "intent": state["plan"].task,
                "activities": state.get("activities", []),
            },
            guard=state.get("guard", {}),
            memory=state.get("memory", {}),
        )

    def _build_graph(self):
        graph = StateGraph(ChatGraphState)
        graph.add_node("input_guard", self._input_guard)
        graph.add_node("load_memory", self._load_memory)
        graph.add_node("plan_query", self._plan_query)
        graph.add_node("list_posts", self._list_posts)
        graph.add_node("summarize_posts", self._summarize_posts)
        graph.add_node("answer_from_posts", self._summarize_posts)
        graph.add_node("semantic_search_posts", self._semantic_search_posts)
        graph.add_node("general_rag", self._general_rag)
        graph.add_node("no_result", self._no_result)
        graph.add_node("generate_answer", self._generate_answer)
        graph.add_node("output_guard", self._output_guard_node)

        graph.add_edge(START, "input_guard")
        graph.add_edge("input_guard", "load_memory")
        graph.add_edge("load_memory", "plan_query")
        graph.add_conditional_edges(
            "plan_query",
            self._route_plan,
            {
                "list_posts": "list_posts",
                "summarize_posts": "summarize_posts",
                "answer_from_posts": "answer_from_posts",
                "semantic_search_posts": "semantic_search_posts",
                "general_rag": "general_rag",
                "no_result": "no_result",
            },
        )
        for node in [
            "list_posts",
            "summarize_posts",
            "answer_from_posts",
            "semantic_search_posts",
            "general_rag",
            "no_result",
        ]:
            graph.add_edge(node, "generate_answer")
        graph.add_edge("generate_answer", "output_guard")
        graph.add_edge("output_guard", END)
        return graph.compile()

    def _input_guard(self, state: ChatGraphState) -> dict[str, Any]:
        result = self._prompt_guard.inspect(state["query"])
        if result.action == "block":
            raise PolicyViolationError(result)
        self._record_activity(state, "guard", "질문 안전성 확인", "completed")
        return {
            "safe_query": result.sanitized_text,
            "guard": result.to_metadata(),
        }

    def _load_memory(self, state: ChatGraphState) -> dict[str, Any]:
        memory_context = self._memory_service.build(
            state["safe_query"],
            state.get("messages", []),
            state.get("stored_memory"),
        )
        if memory_context.used:
            self._record_activity(
                state,
                "memory",
                (
                    "긴 대화 요약 반영"
                    if memory_context.compressed
                    else "이전 대화 맥락 확인"
                ),
                "completed",
            )
        if memory_context.rewritten:
            self._record_activity(
                state,
                "rewrite",
                "후속 질문 맥락 보정",
                "completed",
            )
        return {
            "memory_context": memory_context,
            "memory": memory_context.to_metadata(),
            "search_query": memory_context.rewritten_query,
        }

    def _plan_query(self, state: ChatGraphState) -> dict[str, Any]:
        self._record_activity(state, "plan", "질문 의도 분석", "running")
        plan = normalize_plan(
            self._planner.plan(
                query=state["search_query"],
                memory=state["memory_context"],
                now=datetime.now(KST),
            )
        )
        self._record_activity(state, "plan", "조회 계획 수립", "completed")
        return {"plan": plan}

    def _route_plan(self, state: ChatGraphState) -> str:
        return state["plan"].task

    def _list_posts(self, state: ChatGraphState) -> dict[str, Any]:
        self._record_activity(state, "list_posts", "포스트 목록 조회", "running")
        result = self._post_query.list_posts(state["plan"].constraints)
        self._record_activity(state, "list_posts", "포스트 목록 조회", "completed")
        return {"tool_result": result}

    def _summarize_posts(self, state: ChatGraphState) -> dict[str, Any]:
        self._record_activity(state, "list_posts", "포스트 목록 조회", "running")
        result = self._post_query.list_posts(state["plan"].constraints)
        self._record_activity(state, "list_posts", "포스트 목록 조회", "completed")
        if should_return_no_result(state["plan"], result):
            return {"tool_result": result}

        self._record_activity(state, "read_posts", "본문/요약 조회", "running")
        posts = self._post_query.hydrate_content(result.posts)
        result.posts = posts
        result.context = _build_post_context(posts)
        self._record_activity(state, "read_posts", "본문/요약 조회", "completed")
        return {"tool_result": result}

    def _semantic_search_posts(self, state: ChatGraphState) -> dict[str, Any]:
        plan = state["plan"]
        if plan.strict_scope and plan.constraints.has_scope():
            return self._summarize_posts(state)

        self._record_activity(state, "search", "내용 기반 검색", "running")
        result = self._semantic_search.search(state["search_query"], plan.constraints)
        self._record_activity(state, "search", "내용 기반 검색", "completed")
        return {"tool_result": result}

    def _general_rag(self, state: ChatGraphState) -> dict[str, Any]:
        self._record_activity(state, "search", "관련 글 검색", "running")
        result = self._semantic_search.search(state["search_query"], None)
        self._record_activity(state, "search", "관련 글 검색", "completed")
        return {"tool_result": result}

    def _no_result(self, state: ChatGraphState) -> dict[str, Any]:
        return {
            "tool_result": ToolResult(
                status="no_result",
                message="요청 조건에 맞는 포스트를 찾지 못했습니다.",
            )
        }

    def _generate_answer(self, state: ChatGraphState) -> dict[str, Any]:
        self._record_activity(state, "answer", "답변 생성", "running")
        answer = self._answer_generator.generate(
            query=state["safe_query"],
            plan=state["plan"],
            tool_result=state["tool_result"],
            memory=state["memory_context"],
        )
        self._record_activity(state, "answer", "답변 생성", "completed")
        return {
            "answer": answer,
            "sources": [source.to_dict() for source in state["tool_result"].sources],
        }

    def _output_guard_node(self, state: ChatGraphState) -> dict[str, Any]:
        guard_result = self._output_guard.inspect(state["answer"])
        if guard_result.action == "block":
            return {
                "answer": guard_result.sanitized_text,
                "guard": guard_result.to_metadata(),
            }
        return {"answer": guard_result.sanitized_text}

    def _record_activity(
        self,
        state: ChatGraphState,
        activity_type: str,
        label: str,
        status: str,
    ) -> None:
        activity = {"type": activity_type, "label": label, "status": status}
        activities = state.setdefault("activities", [])
        target_index = next(
            (
                index
                for index, current in enumerate(activities)
                if current["type"] == activity_type and current["label"] == label
            ),
            -1,
        )
        if target_index < 0 and status != "running":
            target_index = next(
                (
                    index
                    for index, current in enumerate(activities)
                    if current["type"] == activity_type
                    and current["status"] == "running"
                ),
                -1,
            )
        if target_index >= 0:
            activities[target_index] = activity
        else:
            activities.append(activity)
        callback = state.get("on_activity")
        if callable(callback):
            callback(activity)


def _build_post_context(posts: list[PostRecord]) -> str:
    parts: list[str] = []
    for index, post in enumerate(posts, 1):
        content = post.plain_text or post.summary
        parts.append(
            "\n".join(
                [
                    f"[Post {index}]",
                    f"Title: {post.title}",
                    f"Blog: {post.blog_name}",
                    f"Published At: {post.published_at}",
                    f"Link: {post.link}",
                    'Content: """',
                    content or "본문/요약 없음",
                    '"""',
                ]
            )
        )
    return "\n\n".join(parts)
