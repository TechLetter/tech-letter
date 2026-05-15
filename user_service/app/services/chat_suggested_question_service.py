from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..models.chat_suggested_question import ChatSuggestedQuestion
from ..repositories.chat_suggested_question_repository import (
    ChatSuggestedQuestionRepository,
)


class DuplicateSuggestedQuestionError(ValueError):
    pass


class SuggestedQuestionNotFoundError(ValueError):
    pass


@dataclass(slots=True)
class SuggestedQuestionMutation:
    text: str
    sort_order: int | None = None
    is_active: bool = True


class ChatSuggestedQuestionService:
    def __init__(self, repo: ChatSuggestedQuestionRepository):
        self.repo = repo

    def list_questions(
        self, *, include_inactive: bool = False
    ) -> list[ChatSuggestedQuestion]:
        return self.repo.list(include_inactive=include_inactive)

    def create_question(
        self, mutation: SuggestedQuestionMutation
    ) -> ChatSuggestedQuestion:
        text = _clean_text(mutation.text)
        normalized_text = _normalize_text(text)
        if self.repo.find_by_normalized_text(normalized_text):
            raise DuplicateSuggestedQuestionError("duplicate suggested question")

        now = datetime.utcnow()
        sort_order = (
            mutation.sort_order
            if mutation.sort_order is not None
            else self.repo.next_sort_order()
        )
        return self.repo.create(
            ChatSuggestedQuestion(
                text=text,
                sort_order=sort_order,
                is_active=mutation.is_active,
                created_at=now,
                updated_at=now,
            ),
            normalized_text=normalized_text,
        )

    def update_question(
        self, question_id: str, mutation: SuggestedQuestionMutation
    ) -> ChatSuggestedQuestion:
        text = _clean_text(mutation.text)
        normalized_text = _normalize_text(text)
        if self.repo.find_by_normalized_text(normalized_text, exclude_id=question_id):
            raise DuplicateSuggestedQuestionError("duplicate suggested question")

        updated = self.repo.update(
            question_id,
            text=text,
            normalized_text=normalized_text,
            sort_order=mutation.sort_order if mutation.sort_order is not None else 0,
            is_active=mutation.is_active,
        )
        if not updated:
            raise SuggestedQuestionNotFoundError("suggested question not found")
        return updated

    def delete_question(self, question_id: str) -> None:
        if not self.repo.delete(question_id):
            raise SuggestedQuestionNotFoundError("suggested question not found")


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise ValueError("suggested question text is required")
    if len(cleaned) > 500:
        raise ValueError("suggested question text must be 500 characters or less")
    return cleaned


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()
