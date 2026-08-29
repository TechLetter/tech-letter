"""Qdrant 컬렉션 이름 규칙 — 운영 데이터에 이미 박혀 있어 바꿀 수 없다."""

from __future__ import annotations

import pytest

from techletter.core.db.qdrant import collection_name_for, normalize_model_name

BASE = "tech_letter_posts"


def test_the_production_collection_name_is_reproduced() -> None:
    """운영에 존재하는 실제 컬렉션 이름이다."""
    assert (
        collection_name_for(BASE, "gemini-embedding-001", 3072)
        == "tech_letter_posts__gemini-embedding-001__3072"
    )


@pytest.mark.parametrize(
    "model",
    ["gemini-embedding-001", "google/gemini-embedding-001", "models/gemini-embedding-001"],
)
def test_provider_prefixes_do_not_split_the_collection(model: str) -> None:
    """OpenRouter를 경유하면 prefix가 붙지만 모델은 같다."""
    assert collection_name_for(BASE, model, 3072) == collection_name_for(
        BASE, "gemini-embedding-001", 3072
    )


def test_model_names_are_slugified() -> None:
    assert (
        collection_name_for(BASE, "Text Embed@v2!", 768) == "tech_letter_posts__text_embed_v2__768"
    )


def test_an_empty_model_name_becomes_unknown() -> None:
    assert normalize_model_name("") == "unknown"
    assert collection_name_for(BASE, "", 8).endswith("__unknown__8")


def test_dimension_is_part_of_the_name() -> None:
    """차원이 다르면 같은 컬렉션에 넣을 수 없다."""
    assert collection_name_for(BASE, "m", 768) != collection_name_for(BASE, "m", 3072)
