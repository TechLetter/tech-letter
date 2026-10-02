"""검색 결과 AI 요약.

검색 결과 상위 글의 저장된 요약으로 짧은 답을 만든다. 무료 모델 호출 한 번이라
크레딧을 받지 않는다. 대신 같은 검색어와 같은 글이면 **7일 동안 저장한 답을
다시 준다**. 결과 화면이 열리면 프론트가 바로 부르므로, 캐시가 없으면 새로고침할
때마다 모델을 부르게 된다.

무료 모델의 하루 한도는 요약 워커의 폴백·모델 헬스체크와 함께 쓴다. 그래서
캐시에 없는 요청만 사용자별 분당 횟수로 묶는다.

"이어서 묻기"를 누를 때만 그 질문과 답을 담은 챗봇 세션을 만든다. 요약을 볼
때마다 세션을 만들면 아무도 열지 않는 대화가 쌓인다.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING

from techletter.chat.memory import MemoryContext
from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.errors import (
    LlmRateLimitedError,
    LlmUnavailableError,
    QuotaExceededError,
    ResourceNotFoundError,
    RetryableError,
)
from techletter.core.logging import get_logger
from techletter.core.time import utcnow
from techletter.search.service import EmbedRateLimiter

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.chat.agent import ChatAgent
    from techletter.chat.sessions import ChatSessionService

__all__ = ["COLLECTION", "SearchSummary", "SearchSummaryService", "summary_key"]

logger = get_logger(__name__)

COLLECTION = "search_summaries"
TTL_SECONDS = 7 * 24 * 3600
# 답변은 상위 5편만 근거로 쓴다(`chat.agent.graph.BRIEF_MAX_POSTS`). 키도 그만큼만 본다.
KEY_POSTS = 5
MISSES_PER_MINUTE = 6

register_indexes(
    COLLECTION,
    [
        IndexSpec(
            "ttl_search_summary", [("created_at", ASCENDING)], expire_after_seconds=TTL_SECONDS
        )
    ],
)


def summary_key(query: str, post_ids: list[str]) -> str:
    """검색어(대소문자·공백 무시)와 상위 글 순서가 같으면 같은 요약이다."""
    normalized = " ".join(query.lower().split())
    raw = normalized + "\n" + ",".join(post_ids[:KEY_POSTS])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass(slots=True)
class SearchSummary:
    key: str
    query: str
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    model_id: str | None = None
    cached: bool = False


class SearchSummaryService:
    def __init__(
        self,
        db: AsyncDatabase,
        agent: ChatAgent,
        sessions: ChatSessionService,
        *,
        misses_per_minute: int = MISSES_PER_MINUTE,
    ) -> None:
        self._col = db[COLLECTION]
        self._agent = agent
        self._sessions = sessions
        self._limiter = EmbedRateLimiter(misses_per_minute)
        # 같은 요약을 동시에 두 번 만들지 않는다(탭 두 개, 빠른 새로고침).
        self._inflight: dict[str, asyncio.Task[SearchSummary]] = {}

    async def summarize(self, user_code: str, query: str, post_ids: list[str]) -> SearchSummary:
        key = summary_key(query, post_ids)

        doc = await self._col.find_one({"_id": key})
        if doc is not None:
            return _from_doc(doc, cached=True)

        task = self._inflight.get(key)
        if task is None:
            if not self._limiter.allow(user_code):
                raise LlmRateLimitedError()
            task = asyncio.create_task(self._generate(key, query.strip(), post_ids))
            self._inflight[key] = task
            task.add_done_callback(lambda _: self._inflight.pop(key, None))
        # 요청이 끊겨도 만들던 요약은 끝까지 만들어 저장한다.
        return await asyncio.shield(task)

    async def _generate(self, key: str, query: str, post_ids: list[str]) -> SearchSummary:
        try:
            result = await self._agent.run(query, MemoryContext(), post_ids=post_ids)
        except QuotaExceededError as exc:
            raise LlmRateLimitedError() from exc
        except RetryableError as exc:
            raise LlmUnavailableError() from exc

        summary = SearchSummary(
            key=key,
            query=query,
            answer=result.answer,
            sources=result.sources,
            model_id=result.model_id,
        )
        # 근거 글이 없거나 출력이 막힌 답은 저장하지 않는다. 다음에 다시 만든다.
        if result.sources and not result.guard:
            await self._col.replace_one(
                {"_id": key},
                {
                    "_id": key,
                    "query": query,
                    "post_ids": post_ids[:KEY_POSTS],
                    "answer": summary.answer,
                    "sources": summary.sources,
                    "model_id": summary.model_id,
                    "created_at": utcnow(),
                },
                upsert=True,
            )
        return summary

    async def continue_in_chat(self, user_code: str, key: str) -> str:
        """저장된 요약의 질문과 답으로 챗봇 세션을 만들고 id를 준다."""
        doc = await self._col.find_one({"_id": key})
        if doc is None:
            raise ResourceNotFoundError("search summary expired")
        summary = _from_doc(doc, cached=True)
        session = await self._sessions.create(user_code, summary.query)
        await self._sessions.append(
            session,
            "assistant",
            summary.answer,
            metadata={
                "sources": summary.sources,
                "agent": {"mode": "search_summary", "model_id": summary.model_id},
            },
        )
        return str(session.id)


def _from_doc(doc: dict[str, Any], *, cached: bool) -> SearchSummary:
    return SearchSummary(
        key=str(doc["_id"]),
        query=str(doc.get("query") or ""),
        answer=str(doc.get("answer") or ""),
        sources=list(doc.get("sources") or []),
        model_id=doc.get("model_id"),
        cached=cached,
    )
