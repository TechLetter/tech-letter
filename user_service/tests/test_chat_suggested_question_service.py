from __future__ import annotations

from datetime import datetime

import pytest

from user_service.app.models.chat_suggested_question import ChatSuggestedQuestion
from user_service.app.services.chat_suggested_question_service import (
    ChatSuggestedQuestionService,
    DuplicateSuggestedQuestionError,
    SuggestedQuestionMutation,
)


class FakeSuggestedQuestionRepository:
    def __init__(self) -> None:
        self.items: list[ChatSuggestedQuestion] = []
        self.normalized_by_id: dict[str, str] = {}

    def list(self, include_inactive: bool = False) -> list[ChatSuggestedQuestion]:
        items = self.items if include_inactive else [
            item for item in self.items if item.is_active
        ]
        return sorted(items, key=lambda item: (item.sort_order, item.created_at))

    def create(
        self, question: ChatSuggestedQuestion, normalized_text: str
    ) -> ChatSuggestedQuestion:
        question.id = question.id or f"question-{len(self.items) + 1}"
        self.items.append(question)
        self.normalized_by_id[question.id] = normalized_text
        return question

    def update(
        self,
        question_id: str,
        *,
        text: str,
        normalized_text: str,
        sort_order: int,
        is_active: bool,
    ) -> ChatSuggestedQuestion | None:
        for item in self.items:
            if item.id == question_id:
                item.text = text
                item.sort_order = sort_order
                item.is_active = is_active
                item.updated_at = datetime.utcnow()
                self.normalized_by_id[question_id] = normalized_text
                return item
        return None

    def delete(self, question_id: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.id != question_id]
        self.normalized_by_id.pop(question_id, None)
        return len(self.items) < before

    def find_by_normalized_text(
        self,
        normalized_text: str,
        exclude_id: str | None = None,
    ) -> ChatSuggestedQuestion | None:
        for item in self.items:
            if item.id == exclude_id:
                continue
            if item.id and self.normalized_by_id.get(item.id) == normalized_text:
                return item
        return None

    def next_sort_order(self) -> int:
        if not self.items:
            return 10
        return max(item.sort_order for item in self.items) + 10


def test_list_questions_returns_empty_when_no_questions_exist() -> None:
    repo = FakeSuggestedQuestionRepository()
    service = ChatSuggestedQuestionService(repo)

    assert service.list_questions() == []


def test_create_question_rejects_duplicate_text() -> None:
    repo = FakeSuggestedQuestionRepository()
    service = ChatSuggestedQuestionService(repo)

    service.create_question(SuggestedQuestionMutation(text="AI Agent 활용 사례"))

    with pytest.raises(DuplicateSuggestedQuestionError):
        service.create_question(SuggestedQuestionMutation(text=" ai  agent 활용 사례 "))


def test_list_questions_hides_inactive_by_default() -> None:
    repo = FakeSuggestedQuestionRepository()
    service = ChatSuggestedQuestionService(repo)

    service.create_question(
        SuggestedQuestionMutation(text="활성 질문", sort_order=10, is_active=True)
    )
    service.create_question(
        SuggestedQuestionMutation(text="비활성 질문", sort_order=20, is_active=False)
    )

    assert [question.text for question in service.list_questions()] == ["활성 질문"]
    assert len(service.list_questions(include_inactive=True)) == 2
