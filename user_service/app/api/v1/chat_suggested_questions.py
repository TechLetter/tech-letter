from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.chat_suggested_question import ChatSuggestedQuestion
from app.repositories.chat_suggested_question_repository import (
    ChatSuggestedQuestionRepository,
)
from app.services.chat_suggested_question_service import (
    ChatSuggestedQuestionService,
    DuplicateSuggestedQuestionError,
    SuggestedQuestionMutation,
    SuggestedQuestionNotFoundError,
)
from common.mongo.client import get_database as get_db

router = APIRouter()


def get_chat_suggested_question_service(
    db=Depends(get_db),
) -> ChatSuggestedQuestionService:
    repo = ChatSuggestedQuestionRepository(db)
    return ChatSuggestedQuestionService(repo)


class SuggestedQuestionMutationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool = True


class SuggestedQuestionResponse(BaseModel):
    id: str
    text: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_response(question: ChatSuggestedQuestion) -> SuggestedQuestionResponse:
    return SuggestedQuestionResponse(
        id=question.id or "",
        text=question.text,
        sort_order=question.sort_order,
        is_active=question.is_active,
        created_at=question.created_at,
        updated_at=question.updated_at,
    )


@router.get("", response_model=list[SuggestedQuestionResponse])
def list_suggested_questions(
    include_inactive: bool = Query(default=False),
    service: ChatSuggestedQuestionService = Depends(
        get_chat_suggested_question_service
    ),
):
    questions = service.list_questions(include_inactive=include_inactive)
    return [_to_response(question) for question in questions]


@router.post("", response_model=SuggestedQuestionResponse)
def create_suggested_question(
    body: SuggestedQuestionMutationRequest,
    service: ChatSuggestedQuestionService = Depends(
        get_chat_suggested_question_service
    ),
):
    try:
        question = service.create_question(
            SuggestedQuestionMutation(
                text=body.text,
                sort_order=body.sort_order,
                is_active=body.is_active,
            )
        )
    except DuplicateSuggestedQuestionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(question)


@router.put("/{question_id}", response_model=SuggestedQuestionResponse)
def update_suggested_question(
    question_id: str,
    body: SuggestedQuestionMutationRequest,
    service: ChatSuggestedQuestionService = Depends(
        get_chat_suggested_question_service
    ),
):
    try:
        question = service.update_question(
            question_id,
            SuggestedQuestionMutation(
                text=body.text,
                sort_order=body.sort_order,
                is_active=body.is_active,
            ),
        )
    except DuplicateSuggestedQuestionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SuggestedQuestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(question)


@router.delete("/{question_id}")
def delete_suggested_question(
    question_id: str,
    service: ChatSuggestedQuestionService = Depends(
        get_chat_suggested_question_service
    ),
):
    try:
        service.delete_question(question_id)
    except SuggestedQuestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": "deleted"}
