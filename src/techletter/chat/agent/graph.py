"""에이전트 실행.

흐름: 범위 읽기(코드) → 근거 모으기(하이브리드 검색 → 글 안의 청크) → 답변 LLM 1회.

- 목록 요청은 LLM 없이 제목·링크를 나열한다.
- "거기서", "그 글"처럼 직전 답을 가리키면 그 답의 출처 글 안에서 답한다.
- 짧은 후속 질문("보안은?")은 직전 질문을 붙여 검색한다. LLM 재작성은 하지 않는다.
- `post_ids`(검색 결과 AI 요약)는 고른 글의 요약본만 읽고 짧게 답한다.

예전의 LLM 플래너(작업 6종 JSON)와 질문 재작성은 없앴다. 플래너가 없는 블로그·태그를
지어내 관련 글을 놓쳤고(2026-09-27 기준선 20문항 중 3건), 재작성은 후속 질문마다
호출을 하나 더 썼다.

에이전트 인스턴스는 프로세스마다 하나이고 요청 여러 개가 동시에 쓴다. 실행별 상태는
지역 변수에 둔다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from techletter.chat.agent.answer import build_post_context, format_post_list
from techletter.chat.agent.prompts import NO_MATCH_ANSWER
from techletter.chat.agent.scope import BlogRef, Scope, is_reference, read_scope
from techletter.chat.agent.state import Activity, PostConstraints, ToolResult
from techletter.chat.guards import OutputGuard
from techletter.content.models import ListPostsFilter
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from techletter.chat.agent.answer import AnswerGenerator
    from techletter.chat.agent.evidence import EvidenceBuilder
    from techletter.chat.agent.tools import PostLookupTool
    from techletter.chat.memory import MemoryContext
    from techletter.content.repositories import BlogRepository

__all__ = ["ActivityRecorder", "AgentResult", "ChatAgent"]

logger = get_logger(__name__)

BRIEF_MAX_POSTS = 5
_BLOGS_TTL_SECONDS = 600

# 목록 요청에서 검색어가 아닌 말. 이것을 빼고도 남는 말이 있으면 그 말로 검색해 나열한다.
_LIST_NOISE = re.compile(
    r"목록|리스트업|리스트|보여\s*줘|알려\s*줘|뽑아\s*줘|추천\s*해?\s*줘|정리\s*해?\s*줘|"
    r"이번\s*주|지난\s*주|이번\s*달|지난\s*달|\d+\s*(?:개|편|건|월|년)|\([^)]*\)|[?.!,~]",
    re.I,
)
_LIST_STOPWORDS = frozenset(
    {
        "좀",
        "최근",
        "최신",
        "요즘",
        "새로",
        "새로운",
        "올라온",
        "나온",
        "쓴",
        "글",
        "글들",
        "포스트",
        "아티클",
        "게시물",
        "블로그",
        "기술",
        "테크",
        "카테고리",
        "주제",
        "관련",
        "관련된",
        "대한",
        "대해",
        "위주",
        "있어",
        "있나",
        "뭐",
        "어떤",
        "무슨",
        "오늘",
        "어제",
        "올해",
        "작년",
        "만",
    }
)
_TOPIC_WORD = re.compile(r"카테고리|주제")
_PARTICLE = re.compile(r"(?:에서|으로|에는|에도|에|의|은|는|이|가|을|를|로|도|만|들)$")
# 이보다 뜻 있는 말이 적은 후속 질문은 직전 질문을 붙여 검색한다("보안 문제는?").
_FOLLOW_UP_MIN_TERMS = 3


def _terms(text: str) -> list[str]:
    """조사를 뗀 두 글자 이상의 낱말."""
    words = (_PARTICLE.sub("", w) for w in re.split(r"\s+", text))
    return [w for w in words if len(w) >= 2 and w not in _LIST_STOPWORDS]


_LABELS = {
    "search": "관련 글 검색",
    "list_posts": "포스트 목록 조회",
    "read_posts": "본문/요약 조회",
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


@dataclass(slots=True)
class AgentResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    intent: str = "general_rag"
    activities: list[dict[str, str]] = field(default_factory=list)
    guard: dict[str, Any] = field(default_factory=dict)
    model_id: str | None = None


def _no_match(answer: str) -> bool:
    """모델이 "관련 글을 찾지 못했습니다"로 시작하면 뒤에 설명을 붙였어도 없는 것이다."""
    return answer.strip().startswith(NO_MATCH_ANSWER)


_CITATION = re.compile(r"\s*\[\d{1,2}\](?:\[\d{1,2}\])*")
_NO_MATCH_NOTE_CHARS = 300


def _no_match_answer(answer: str) -> str:
    """출처를 비우니 `[n]`은 지운다. 덧붙인 설명은 짧게 남긴다(무엇은 있는지, 왜 범위 밖인지)."""
    text = _CITATION.sub("", answer.strip())
    return text if len(text) <= _NO_MATCH_NOTE_CHARS else text[:_NO_MATCH_NOTE_CHARS].rstrip() + "…"


def _describe(scope: Scope) -> str:
    parts = [
        p for p in (scope.period_label, f"{scope.blog.name} 블로그" if scope.blog else "") if p
    ]
    return " ".join(parts)


class ChatAgent:
    def __init__(
        self,
        *,
        evidence: EvidenceBuilder,
        posts: PostLookupTool,
        answers: AnswerGenerator,
        blogs: BlogRepository | None = None,
        output_guard: OutputGuard | None = None,
    ) -> None:
        self._evidence = evidence
        self._posts = posts
        self._answers = answers
        self._blog_repo = blogs
        self._blogs: list[BlogRef] = []
        self._blogs_at = 0.0
        # 검색 AI 요약에만 쓴다. 챗봇 답변은 덮어쓰지 않는다.
        self._output_guard = output_guard or OutputGuard()

    async def _known_blogs(self) -> list[BlogRef]:
        if self._blog_repo is None:
            return []
        if not self._blogs or time.monotonic() - self._blogs_at > _BLOGS_TTL_SECONDS:
            try:
                active = await self._blog_repo.list_active()
                self._blogs = [BlogRef(str(b.id), b.name) for b in active]
                self._blogs_at = time.monotonic()
            except Exception:
                logger.warning("blog list failed; scope without blogs", exc_info=True)
        return self._blogs

    # ── 실행 ───────────────────────────────────────────────────────
    async def run(
        self,
        query: str,
        memory: MemoryContext,
        on_activity: Callable[[Activity], Awaitable[None]] | None = None,
        *,
        model_id: str | None = None,
        post_ids: list[str] | None = None,
        client: str | None = None,
    ) -> AgentResult:
        recorder = ActivityRecorder(on_activity)
        if post_ids:
            return await self._brief(query, post_ids, recorder)

        scope = read_scope(query, await self._known_blogs())
        flt = ListPostsFilter(
            summarized=True,
            blog_id=scope.blog.id if scope.blog else None,
            published_from=scope.published_from,
            published_to=scope.published_to,
        )
        boost = scope.boost_blog.id if scope.boost_blog else None
        if scope.unknown_blog:
            return AgentResult(
                answer=f"'{scope.unknown_blog}' 블로그는 Tech-Letter가 모으는 블로그에 없습니다.",
                intent="no_result",
                activities=recorder.items,
            )

        if scope.is_list:
            return await self._list(
                query, scope=scope, flt=flt, boost=boost, client=client, recorder=recorder
            )

        await recorder.emit("search", "running")
        if is_reference(query) and memory.previous_source_ids:
            intent = "answer_from_posts"
            result = await self._evidence.for_posts(
                query, memory.previous_source_ids, client=client
            )
        else:
            intent = "general_rag"
            search_text = query
            if memory.previous_query and len(_terms(query)) < _FOLLOW_UP_MIN_TERMS:
                search_text = f"{memory.previous_query} {query}"
            excluding = bool(scope.exclude_blogs)
            result = await self._evidence.for_query(
                search_text,
                flt,
                client=client,
                boost_blog_id=boost,
                # "말고 다른 사례"면 직전 답의 글과 이름이 나온 블로그를 뺀다.
                exclude_ids=frozenset(memory.previous_source_ids) if excluding else frozenset(),
                exclude_blog_ids=frozenset(b.id for b in scope.exclude_blogs),
            )
        await recorder.emit("search", "completed")

        if result.status != "ok":
            described = _describe(scope)
            message = (
                f"{described} 조건에 맞는 글을 찾지 못했습니다." if described else NO_MATCH_ANSWER
            )
            return AgentResult(
                answer=message, intent="no_result", activities=recorder.items, model_id=None
            )

        await recorder.emit("answer", "running")
        answer, used = await self._answers.answer(query, result, memory.recent, model_id)
        await recorder.emit("answer", "completed")
        if _no_match(answer):
            return AgentResult(
                answer=_no_match_answer(answer),
                intent="no_result",
                activities=recorder.items,
                model_id=used,
            )
        return AgentResult(
            answer=answer,
            sources=[source.to_dict() for source in result.sources],
            intent=intent,
            activities=recorder.items,
            model_id=used,
        )

    async def _list(
        self,
        query: str,
        *,
        scope: Scope,
        flt: ListPostsFilter,
        boost: str | None,
        client: str | None,
        recorder: ActivityRecorder,
    ) -> AgentResult:
        """목록은 LLM 없이 나열한다. 주제어가 남으면 그 말로 검색한 순서, 아니면 최신순."""
        await recorder.emit("list_posts", "running")
        text = _LIST_NOISE.sub(" ", query)
        if scope.blog:
            text = re.sub(re.escape(scope.blog.name), " ", text, flags=re.I)
        keywords = " ".join(_terms(text))
        # 주제어가 걸려도 다른 낱말이 남으면 그 말로 검색한다("무신사 DB 성능 글 목록").
        # "카테고리", "주제"라고 못 박았을 때만 주제 목록으로 나열한다.
        if len(keywords) >= 2 and not (scope.topics and _TOPIC_WORD.search(query)):
            posts, _ = await self._evidence.rank(
                keywords, flt, client=client, boost_blog_id=boost, limit=scope.limit
            )
            result = self._posts.records(posts, message=f"'{keywords}' 관련 글을 찾았습니다.")
        else:
            result = await self._posts.list_posts(
                PostConstraints(
                    published_from=scope.published_from,
                    published_to=scope.published_to,
                    blog_id=scope.blog.id if scope.blog else None,
                    blog_name=scope.blog.name if scope.blog else None,
                    categories=scope.topics,
                    limit=scope.limit,
                )
            )
        await recorder.emit("list_posts", "completed")
        if result.status != "ok":
            described = _describe(scope)
            message = (
                f"{described} 조건에 맞는 글을 찾지 못했습니다." if described else NO_MATCH_ANSWER
            )
            return AgentResult(answer=message, intent="no_result", activities=recorder.items)
        return AgentResult(
            answer=format_post_list(result),
            sources=[source.to_dict() for source in result.sources],
            intent="list_posts",
            activities=recorder.items,
        )

    async def _brief(
        self, query: str, post_ids: list[str], recorder: ActivityRecorder
    ) -> AgentResult:
        """검색 결과 AI 요약 — 고른 글의 요약본만 읽고 짧게. 출처 번호는 고른 순서다."""
        await recorder.emit("read_posts", "running")
        result: ToolResult = await self._posts.get_posts(post_ids[:BRIEF_MAX_POSTS])
        await recorder.emit("read_posts", "completed")
        if result.status != "ok":
            return AgentResult(answer=result.message, intent="no_result", activities=recorder.items)
        result.context = build_post_context(result.posts, summaries_only=True)
        await recorder.emit("answer", "running")
        answer, used = await self._answers.brief(query, result)
        await recorder.emit("answer", "completed")
        checked = self._output_guard.inspect(answer)
        return AgentResult(
            answer=checked.text,
            sources=[] if checked.blocked else [s.to_dict() for s in result.sources],
            intent="answer_from_posts",
            activities=recorder.items,
            guard=checked.to_metadata() if checked.blocked else {},
            model_id=used,
        )
