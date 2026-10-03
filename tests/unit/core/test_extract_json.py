"""모델 응답에서 JSON 객체 하나를 꺼낸다 — 모델마다 앞뒤에 붙이는 것이 다르다."""

from __future__ import annotations

import pytest

from techletter.core.llm.chat import extract_json
from techletter.core.llm.errors import JsonOutputError


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Here it is:\n{"a": 1}\nThanks',
        '```json\n{"a": 1}\n```\n\nNote: the body is long.',
        '{"a": 1}\n{"b": 2}',
        'Shape {like this}:\n```json\n{"a": 1}\n```',
    ],
)
def test_the_first_object_is_returned(raw: str) -> None:
    assert extract_json(raw) == {"a": 1}


def test_braces_inside_strings_are_kept() -> None:
    assert extract_json('{"body_md": "use {x} and ```code```"} trailing') == {
        "body_md": "use {x} and ```code```"
    }


def test_raw_newlines_inside_strings_are_accepted() -> None:
    raw = '{"body_md": "## 배경\n본문"}'  # 문자열 안의 줄바꿈이 이스케이프되지 않았다

    assert extract_json(raw) == {"body_md": "## 배경\n본문"}


@pytest.mark.parametrize("raw", ["no json", '{"a": 1, "tldr": {"x": 2}', "[1, 2]"])
def test_broken_answers_fail(raw: str) -> None:
    """잘린 응답에서 안쪽 객체를 답으로 삼지 않는다."""
    with pytest.raises(JsonOutputError):
        extract_json(raw)
