"""글 "쉽게 읽기" — 원문을 한국어로 풀어 다시 쓴 설명 글.

번역이 아니다. 기술 블로그는 모두 저작권을 유보하고 있어(2026-10-03 조사) 원문 문장을
옮기지 않고 새로 쓴다. 짧은 인용만 블록인용으로 남긴다. 저장은 `post_explainers` 컬렉션이다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from techletter.core.db.documents import BaseDocument, MongoDateTime, PyObjectId, SubDocument
from techletter.core.time import utcnow

__all__ = ["Explainer", "ExplainerChecks", "Generation", "GlossaryItem", "Tldr"]

PostType = Literal["research", "case", "tutorial", "news"]
Difficulty = Literal["beginner", "intermediate", "advanced"]


class Tldr(SubDocument):
    one_liner: str = ""
    """카드·검색·챗봇이 쓰는 한 문장. `aisummary.summary` 자리에도 들어간다."""
    points: list[str] = Field(default_factory=list)


class GlossaryItem(SubDocument):
    term: str
    original: str = ""
    explanation: str = ""


class ExplainerChecks(SubDocument):
    """코드로 대조한 결과. LLM 판정보다 숫자·이름 오류를 잘 잡는다."""

    length_ok: bool = True
    quote_ratio: float = 0.0
    quote_ok: bool = True
    numbers_missing: list[str] = Field(default_factory=list)
    code_ok: bool = True
    copy_ratio: float = 0.0
    """본문 중 원문을 30자 이상 그대로 옮긴 구간의 비율(인용 포함)."""
    copy_ok: bool = True
    korean_ok: bool = True
    """본문 글자의 대부분이 한글이고, 원문에 없는 일본어·러시아어 등이 섞이지 않았는가."""
    sections_ok: bool = True
    """분량에 맞게 "## " 섹션을 나눴는가. 요약으로 뭉개면 섹션이 적다."""
    style_ok: bool = True
    """v5 문체 규칙(`~다` 평서체, 담백한 명사 제목, AI 문체 장치 없음, bullet 사용)을 지켰는가."""
    style_issues: list[str] = Field(default_factory=list)
    """어긴 문체 규칙. 재시도 피드백에 그대로 쓴다."""

    @property
    def passed(self) -> bool:
        return (
            self.length_ok
            and self.quote_ok
            and self.code_ok
            and self.copy_ok
            and not self.numbers_missing
            and self.korean_ok
            and self.sections_ok
            and self.style_ok
        )


class Generation(SubDocument):
    generator: Literal["gemini", "codex_backfill", "openrouter"] = "gemini"
    model: str = ""
    prompt_version: str = ""
    source_chars: int = 0
    source_hash: str = ""
    generated_at: MongoDateTime = Field(default_factory=utcnow)


class Explainer(BaseDocument):
    post_id: PyObjectId
    post_type: PostType = "case"
    difficulty: Difficulty = "intermediate"
    reading_minutes: int = 1
    tldr: Tldr = Field(default_factory=Tldr)
    body_md: str = ""
    glossary: list[GlossaryItem] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    checks: ExplainerChecks = Field(default_factory=ExplainerChecks)
    generation: Generation = Field(default_factory=Generation)
