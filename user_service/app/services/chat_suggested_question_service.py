from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..models.chat_suggested_question import ChatSuggestedQuestion
from ..repositories.chat_suggested_question_repository import (
    ChatSuggestedQuestionRepository,
)


DEFAULT_SUGGESTED_QUESTIONS = [
    "AI Agent를 실제 서비스에 도입할 때 LangGraph 같은 워크플로 엔진을 언제 쓰면 좋을까?",
    "Kubernetes에서 AI 추론 워크로드를 운영할 때 GPU 스케줄링과 비용을 어떻게 최적화할 수 있을까?",
    "RAG 시스템에서 벡터 검색과 메타데이터 필터링을 함께 쓰는 하이브리드 검색 사례를 찾아줘.",
    "프롬프트 인젝션과 데이터 유출을 막기 위한 LLM 보안 설계 사례를 알려줘.",
    "플랫폼 엔지니어링과 Internal Developer Platform이 개발 생산성에 어떤 영향을 주는지 사례를 찾아줘.",
    "AI 코딩 에이전트를 CI/CD에 붙일 때 코드 리뷰와 품질 관리는 어떻게 해야 할까?",
    "관측성에서 OpenTelemetry, 로그, 메트릭, 트레이스를 함께 활용한 장애 분석 사례를 알려줘.",
    "Post-Quantum Cryptography 전환을 백엔드 서비스에서 준비하려면 무엇부터 확인해야 할까?",
    "멀티모달 AI를 제품 기능에 붙일 때 아키텍처와 비용 관리 포인트를 알려줘.",
    "클라우드 네이티브 환경에서 서비스 간 이벤트 재시도와 DLQ를 안정적으로 설계한 사례를 찾아줘.",
]


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
        self._ensure_default_questions()
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

    def _ensure_default_questions(self) -> None:
        if self.repo.defaults_seeded():
            return
        if self.repo.count_all() == 0:
            now = datetime.utcnow()
            for index, text in enumerate(DEFAULT_SUGGESTED_QUESTIONS, 1):
                cleaned_text = _clean_text(text)
                self.repo.create(
                    ChatSuggestedQuestion(
                        text=cleaned_text,
                        sort_order=index * 10,
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    ),
                    normalized_text=_normalize_text(cleaned_text),
                )
        self.repo.mark_defaults_seeded()


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise ValueError("suggested question text is required")
    if len(cleaned) > 500:
        raise ValueError("suggested question text must be 500 characters or less")
    return cleaned


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()
