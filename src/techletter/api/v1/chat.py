"""채팅.

스트리밍은 SSE다. 프레이밍(`event:`/`data:`, `\\n\\n` 구분)은 프론트 파서가
그대로 쓰므로 유지한다.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from techletter.api.deps import Ctx, CurrentUser
from techletter.api.schemas import (
    ChatAnswerOut,
    ChatSessionOut,
    Listing,
    MessageIn,
    Paged,
    SuggestedQuestionOut,
)
from techletter.api.schemas.query import StrQ, parse_page
from techletter.core.errors import AppError, InternalError
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

    from techletter.chat.agent import Activity

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # nginx가 SSE를 버퍼링하면 활동 이벤트가 한꺼번에 도착한다.
    "X-Accel-Buffering": "no",
}
KEEPALIVE_SECONDS = 15


def _frame(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/suggested-questions", response_model=Listing[dict])
async def suggested_questions(ctx: Ctx) -> Listing[dict]:
    questions = await ctx.suggested_questions.list()
    return Listing.of([SuggestedQuestionOut.public(q) for q in questions])


@router.get("/sessions", response_model=Paged[ChatSessionOut])
async def list_sessions(
    ctx: Ctx, user: CurrentUser, page: StrQ = None, page_size: StrQ = None
) -> Paged[ChatSessionOut]:
    paging = parse_page(page, page_size)
    rows, total = await ctx.sessions.list(user.user_code, paging)
    return Paged.of_page(
        [ChatSessionOut.summary(row.session, row.message_count) for row in rows], total, paging
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=ChatSessionOut)
async def create_session(ctx: Ctx, user: CurrentUser) -> ChatSessionOut:
    return ChatSessionOut.of(await ctx.sessions.create(user.user_code))


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_session(ctx: Ctx, user: CurrentUser, session_id: str) -> ChatSessionOut:
    return ChatSessionOut.of(await ctx.sessions.get(session_id, user.user_code))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(ctx: Ctx, user: CurrentUser, session_id: str) -> Response:
    await ctx.sessions.delete(session_id, user.user_code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/messages", response_model=ChatAnswerOut)
async def send_message(ctx: Ctx, user: CurrentUser, body: MessageIn) -> ChatAnswerOut:
    answer = await ctx.chat.run(
        user_code=user.user_code, query=body.query, session_id=body.session_id
    )
    return ChatAnswerOut.of(answer)


@router.post("/messages/stream")
async def stream_message(ctx: Ctx, user: CurrentUser, body: MessageIn) -> StreamingResponse:
    """진행 상황을 흘려보내고 마지막에 답변을 준다.

    **가드·세션·크레딧 실패는 스트림이 아니라 일반 JSON 에러로 나간다.**
    스트림을 열어 버리면 HTTP 상태가 이미 200이라 프론트가 402/403을
    구분하지 못한다. 그래서 에이전트 실행을 백그라운드 태스크로 돌리고,
    첫 활동이 오기 전에 난 실패는 그대로 예외로 올린다.
    """
    activities: asyncio.Queue[Activity | None] = asyncio.Queue()

    async def on_activity(activity: Activity) -> None:
        await activities.put(activity)

    task = asyncio.create_task(
        ctx.chat.run(
            user_code=user.user_code,
            query=body.query,
            session_id=body.session_id,
            on_activity=on_activity,
        )
    )

    # 첫 활동(=계획 시작)이 나오면 가드·세션·크레딧을 모두 통과했다는 뜻이다.
    first = await _first_signal(task, activities)

    async def events() -> AsyncIterator[str]:
        pending = [first] if first is not None else []
        try:
            while True:
                for activity in pending:
                    yield _frame("activity", _activity_payload(activity))
                pending = []
                if task.done():
                    break
                try:
                    item = await asyncio.wait_for(activities.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    # 프록시가 조용한 연결을 끊지 않게 한다. 프론트 파서는
                    # `data:` 없는 블록을 무시한다.
                    yield ": keepalive\n\n"
                    continue
                if item is not None:
                    pending = [item]

            answer = await task
            yield _frame("done", ChatAnswerOut.of(answer).model_dump())
        except asyncio.CancelledError:
            task.cancel()
            raise
        except AppError as exc:
            yield _frame("error", exc.to_body())
        except Exception:
            logger.exception("chat stream failed")
            yield _frame("error", InternalError().to_body())
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)


def _activity_payload(activity: Activity) -> dict[str, str]:
    payload = activity.to_dict()
    # 계약은 `done`, 내부는 `completed`다.
    if payload["status"] == "completed":
        payload["status"] = "done"
    return payload


async def _first_signal(task: asyncio.Task, activities: asyncio.Queue) -> Activity | None:
    """첫 활동이나 태스크 종료 중 먼저 오는 것을 기다린다.

    태스크가 먼저 끝났다면 예외가 있을 수 있다 — 여기서 올려야 SSE가 아니라
    JSON 에러로 나간다.
    """
    getter = asyncio.ensure_future(activities.get())
    done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
    if getter in done:
        return getter.result()
    getter.cancel()
    # 태스크가 먼저 끝났다: 예외면 여기서 전파된다.
    task.result()
    return None
