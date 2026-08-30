"""어드민 추천 질문."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from techletter.api.deps import AdminUser, Ctx
from techletter.api.schemas import Listing, SuggestedQuestionIn, SuggestedQuestionOut
from techletter.api.schemas.query import StrQ
from techletter.core.pagination import lenient_bool

router = APIRouter(prefix="/suggested-questions", tags=["admin:suggested-questions"])


@router.get("", response_model=Listing[SuggestedQuestionOut])
async def list_questions(
    ctx: Ctx, _: AdminUser, include_inactive: StrQ = None
) -> Listing[SuggestedQuestionOut]:
    # 다섯 건 남짓이라 페이지를 나누지 않는다.
    questions = await ctx.suggested_questions.list(
        include_inactive=lenient_bool(include_inactive) is not False
    )
    return Listing.of([SuggestedQuestionOut.of(q) for q in questions])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SuggestedQuestionOut)
async def create_question(
    ctx: Ctx, _: AdminUser, body: SuggestedQuestionIn
) -> SuggestedQuestionOut:
    question = await ctx.suggested_questions.create(
        body.text, sort_order=body.sort_order, is_active=body.is_active
    )
    return SuggestedQuestionOut.of(question)


@router.put("/{question_id}", response_model=SuggestedQuestionOut)
async def update_question(
    ctx: Ctx, _: AdminUser, question_id: str, body: SuggestedQuestionIn
) -> SuggestedQuestionOut:
    question = await ctx.suggested_questions.update(
        question_id, text=body.text, sort_order=body.sort_order, is_active=body.is_active
    )
    return SuggestedQuestionOut.of(question)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(ctx: Ctx, _: AdminUser, question_id: str) -> Response:
    await ctx.suggested_questions.delete(question_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
