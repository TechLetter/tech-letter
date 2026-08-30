"""에이전트 그래프.

노드는 전부 async다 — 동기 코드가 섞이면 요청 하나가 이벤트 루프를 통째로 막는다.

흐름: 계획 → (도구 하나) → 답변 → 출력 가드.
입력 가드와 메모리 구성은 그래프 밖에 있다 — 크레딧을 깎기 전에 끝나야 한다.

에이전트 인스턴스는 프로세스마다 하나이고 요청 여러 개가 동시에 쓴다.
그래서 실행별 상태(진행 상황, 콜백)는 **전부 state 안에** 둔다. `self`에
붙이면 동시 요청끼리 활동 목록을 섞어 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from techletter.chat.agent.answer import build_post_context
from techletter.chat.agent.policies import should_return_no_result
from techletter.chat.agent.state import Activity, ChatPlan, ToolResult
from techletter.chat.guards import OutputGuard
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from techletter.chat.agent.answer import AnswerGenerator
    from techletter.chat.agent.planner import QueryPlanner
    from techletter.chat.agent.tools import PostLookupTool, VectorSearchTool
    from techletter.chat.memory import MemoryContext

__all__ = ["ActivityRecorder", "AgentResult", "ChatAgent"]

logger = get_logger(__name__)

_LABELS = {
    "plan": "질문 의도 분석",
    "list_posts": "포스트 목록 조회",
    "read_posts": "본문/요약 조회",
    "search": "내용 기반 검색",
    "answer": "답변 생성",
}


class ActivityRecorder:
    """실행 하나의 진행 상황. 같은 종류는 덮어쓴다.

    프론트는 "조회 중 → 완료"를 한 줄로 보여주므로 항목이 쌓이면 안 된다.
    """

    def __init__(self, sink: Callable[[Activity], Awaitable[None]] | None = None) -> None:
        self._items: list[Activity] = []
        self._sink = sink

    @property
    def items(self) -> list[dict[str, str]]:
        return [item.to_dict() for item in self._items]

    async def emit(self, activity_type: str, status: str) -> None:
        activity = Activity(type=activity_type, label=_LABELS[activity_type], status=status)  # type: ignore[arg-type]
        for index, existing in enumerate(self._items):
            if existing.type == activity_type:
                self._items[index] = activity
                break
        else:
            self._items.append(activity)
        if self._sink is not None:
            await self._sink(activity)


@dataclass
class AgentState:
    """그래프가 주고받는 값. LangGraph가 노드 반환 dict를 병합한다."""

    query: str = ""
    search_query: str = ""
    memory_metadata: dict[str, Any] = field(default_factory=dict)
    recorder: ActivityRecorder = field(default_factory=ActivityRecorder)
    plan: ChatPlan = field(default_factory=ChatPlan)
    tool_result: ToolResult = field(default_factory=ToolResult)
    answer: str = ""


@dataclass(slots=True)
class AgentResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    intent: str = "general_rag"
    activities: list[dict[str, str]] = field(default_factory=list)
    guard: dict[str, Any] = field(default_factory=dict)


class ChatAgent:
    def __init__(
        self,
        *,
        planner: QueryPlanner,
        posts: PostLookupTool,
        search: VectorSearchTool,
        answers: AnswerGenerator,
        output_guard: OutputGuard | None = None,
    ) -> None:
        self._planner = planner
        self._posts = posts
        self._search = search
        self._answers = answers
        self._output_guard = output_guard or OutputGuard()
        self._graph = self._build()

    # ── 그래프 ─────────────────────────────────────────────────────
    def _build(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan)
        graph.add_node("list_posts", self._list_posts)
        graph.add_node("read_posts", self._read_posts)
        graph.add_node("semantic_search_posts", self._semantic_search)
        graph.add_node("general_rag", self._general_rag)
        graph.add_node("no_result", self._no_result)
        graph.add_node("answer", self._answer)

        graph.add_edge(START, "plan")
        graph.add_conditional_edges(
            "plan",
            self._route,
            {
                "list_posts": "list_posts",
                # 요약/본문 기반 답변은 목록을 뽑은 뒤 본문을 채운다.
                "read_posts": "read_posts",
                "semantic_search_posts": "semantic_search_posts",
                "general_rag": "general_rag",
                "no_result": "no_result",
            },
        )
        for node in (
            "list_posts",
            "read_posts",
            "semantic_search_posts",
            "general_rag",
            "no_result",
        ):
            graph.add_edge(node, "answer")
        graph.add_edge("answer", END)
        return graph.compile()

    @staticmethod
    def _route(state: AgentState) -> str:
        task = state.plan.task
        return "read_posts" if task in {"summarize_posts", "answer_from_posts"} else task

    # ── 노드 ───────────────────────────────────────────────────────
    async def _plan(self, state: AgentState) -> dict[str, Any]:
        await state.recorder.emit("plan", "running")
        plan = await self._planner.plan(state.search_query, state.memory_metadata)
        await state.recorder.emit("plan", "completed")
        return {"plan": plan}

    async def _list_posts(self, state: AgentState) -> dict[str, Any]:
        await state.recorder.emit("list_posts", "running")
        result = await self._posts.list_posts(state.plan.constraints)
        await state.recorder.emit("list_posts", "completed")
        return {"tool_result": result}

    async def _read_posts(self, state: AgentState) -> dict[str, Any]:
        await state.recorder.emit("list_posts", "running")
        result = await self._posts.list_posts(state.plan.constraints)
        await state.recorder.emit("list_posts", "completed")
        if should_return_no_result(state.plan, result):
            return {"tool_result": result}

        await state.recorder.emit("read_posts", "running")
        result.posts = await self._posts.hydrate(result.posts)
        result.context = build_post_context(result.posts)
        await state.recorder.emit("read_posts", "completed")
        return {"tool_result": result}

    async def _semantic_search(self, state: AgentState) -> dict[str, Any]:
        # 범위를 못 박은 질문은 메타데이터 조회가 정확하다. 벡터 검색은
        # 날짜·블로그 조건을 지키지 못한다.
        if state.plan.strict_scope and state.plan.constraints.has_scope():
            return await self._read_posts(state)

        await state.recorder.emit("search", "running")
        result = await self._search.search(state.search_query, state.plan.constraints)
        await state.recorder.emit("search", "completed")
        return {"tool_result": result}

    async def _general_rag(self, state: AgentState) -> dict[str, Any]:
        await state.recorder.emit("search", "running")
        result = await self._search.search(state.search_query)
        await state.recorder.emit("search", "completed")
        return {"tool_result": result}

    async def _no_result(self, state: AgentState) -> dict[str, Any]:
        del state  # 조건 없이 고정 응답을 낸다
        return {
            "tool_result": ToolResult(
                status="no_result", message="요청 조건에 맞는 포스트를 찾지 못했습니다."
            )
        }

    async def _answer(self, state: AgentState) -> dict[str, Any]:
        await state.recorder.emit("answer", "running")
        answer = await self._answers.generate(
            state.query, state.plan, state.tool_result, state.memory_metadata
        )
        await state.recorder.emit("answer", "completed")
        return {"answer": answer}

    # ── 실행 ───────────────────────────────────────────────────────
    async def run(
        self,
        query: str,
        memory: MemoryContext,
        on_activity: Callable[[Activity], Awaitable[None]] | None = None,
    ) -> AgentResult:
        recorder = ActivityRecorder(on_activity)
        final = await self._graph.ainvoke(
            AgentState(
                query=query,
                search_query=memory.rewritten_query or query,
                memory_metadata=memory.to_metadata(),
                recorder=recorder,
            )
        )

        result: ToolResult = final["tool_result"]
        plan: ChatPlan = final["plan"]
        checked = self._output_guard.inspect(final["answer"])
        return AgentResult(
            answer=checked.text,
            # 답변이 차단되면 출처도 붙이지 않는다.
            sources=[] if checked.blocked else [source.to_dict() for source in result.sources],
            intent=plan.task,
            activities=recorder.items,
            guard=checked.to_metadata() if checked.blocked else {},
        )
