"""글 "쉽게 읽기" 응답."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.explainer.models import Explainer

__all__ = ["ExplainerOut", "GlossaryOut"]


class GlossaryOut(BaseModel):
    term: str
    original: str
    explanation: str


class ExplainerOut(BaseModel):
    post_id: str
    post_type: str
    difficulty: str
    reading_minutes: int
    one_liner: str
    points: list[str]
    body_md: str
    glossary: list[GlossaryOut]
    generated_at: str | None

    @classmethod
    def of(cls, explainer: Explainer) -> ExplainerOut:
        return cls(
            post_id=str(explainer.post_id),
            post_type=explainer.post_type,
            difficulty=explainer.difficulty,
            reading_minutes=explainer.reading_minutes,
            one_liner=explainer.tldr.one_liner,
            points=explainer.tldr.points,
            body_md=explainer.body_md,
            glossary=[
                GlossaryOut(term=g.term, original=g.original, explanation=g.explanation)
                for g in explainer.glossary
            ],
            generated_at=to_iso_z(explainer.generation.generated_at),
        )
