"""추천 질문 관리(어드민).

중복 검사는 **유니크 인덱스**에 맡긴다. 현행은 `find_one` 후 `insert`라
동시 요청 두 개가 같은 질문을 나란히 넣을 수 있었다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from techletter.chat.models import SuggestedQuestion
from techletter.chat.repositories import normalize_question
from techletter.core.errors import InvalidRequestError, ResourceNotFoundError

if TYPE_CHECKING:  # pragma: no cover
    from techletter.chat.repositories import SuggestedQuestionRepository

__all__ = ["MAX_TEXT_CHARS", "SuggestedQuestionService", "clean_text"]

MAX_TEXT_CHARS = 500


def clean_text(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise InvalidRequestError("추천 질문 내용을 입력해 주세요.", details={"field": "text"})
    if len(cleaned) > MAX_TEXT_CHARS:
        raise InvalidRequestError(
            f"추천 질문은 {MAX_TEXT_CHARS}자 이내여야 합니다.",
            details={"field": "text", "max_length": MAX_TEXT_CHARS},
        )
    return cleaned


class SuggestedQuestionService:
    def __init__(self, questions: SuggestedQuestionRepository) -> None:
        self._questions = questions

    async def list(self, *, include_inactive: bool = False) -> list[SuggestedQuestion]:
        return await self._questions.list_questions(include_inactive=include_inactive)

    async def create(
        self, text: str, *, sort_order: int | None = None, is_active: bool = True
    ) -> SuggestedQuestion:
        cleaned = clean_text(text)
        return await self._questions.create(
            SuggestedQuestion(
                text=cleaned,
                normalized_text=normalize_question(cleaned),
                sort_order=(
                    sort_order
                    if sort_order is not None
                    else await self._questions.next_sort_order()
                ),
                is_active=is_active,
            )
        )

    async def update(
        self,
        question_id: str,
        *,
        text: str | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> SuggestedQuestion:
        """부분 갱신. 현행은 전체 교체라 순번을 안 보내면 0으로 밀렸다."""
        fields: dict[str, object] = {}
        if text is not None:
            cleaned = clean_text(text)
            fields["text"] = cleaned
            fields["normalized_text"] = normalize_question(cleaned)
        if sort_order is not None:
            fields["sort_order"] = sort_order
        if is_active is not None:
            fields["is_active"] = is_active

        if not fields:
            existing = await self._questions.get(question_id)
            if existing is None:
                raise ResourceNotFoundError(f"suggested question not found: {question_id}")
            return existing

        updated = await self._questions.update(question_id, fields)
        if updated is None:
            raise ResourceNotFoundError(f"suggested question not found: {question_id}")
        return updated

    async def delete(self, question_id: str) -> None:
        if not await self._questions.delete(question_id):
            raise ResourceNotFoundError(f"suggested question not found: {question_id}")
