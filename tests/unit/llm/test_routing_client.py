"""`RoutingChatClient` — model_id로 provider를 나눠 보낸다.

컷오버 중 실측한 실제 결함을 고정한다: 요약은 Gemini 1순위(D13) +
OpenRouter 폴백(ADR-0008)인데, 단일 provider짜리 `LangChainChatClient` 하나만
썼더니 라우터가 고른 OpenRouter 후보 model_id(`nvidia/...:free`)가 그대로
Gemini API로 가서 "그런 모델 없다"는 404 `PermanentError`로 죽었다. 실제
프로덕션 백필에서 526건 중 여러 건이 이 경로로 영구 실패했다.
"""

from __future__ import annotations

from techletter.core.llm.chat import RoutingChatClient


class RecordingClient:
    def __init__(self, name: str, reply: str = "ok") -> None:
        self.name = name
        self.reply = reply
        self.calls: list[str] = []
        self.closed = False

    async def complete(self, model_id, system, user, **kwargs):
        self.calls.append(model_id)
        return f"{self.name}:{self.reply}"

    async def aclose(self) -> None:
        self.closed = True


PRIMARY_MODEL = "gemini-3-flash-preview"


def build():
    primary = RecordingClient("primary")
    fallback = RecordingClient("fallback")
    client = RoutingChatClient(PRIMARY_MODEL, primary, fallback)  # type: ignore[arg-type]
    return client, primary, fallback


async def test_the_exact_primary_model_id_goes_to_the_primary_client() -> None:
    client, primary, fallback = build()

    result = await client.complete(PRIMARY_MODEL, "sys", "usr")

    assert result == "primary:ok"
    assert primary.calls == [PRIMARY_MODEL]
    assert fallback.calls == []


async def test_an_openrouter_candidate_never_reaches_the_primary_client() -> None:
    """이게 고쳐진 실제 버그다: Gemini 클라이언트로 OpenRouter 모델을 부르면 404."""
    client, primary, fallback = build()

    result = await client.complete("nvidia/nemotron-3-super-120b-a12b:free", "sys", "usr")

    assert result == "fallback:ok"
    assert fallback.calls == ["nvidia/nemotron-3-super-120b-a12b:free"]
    assert primary.calls == []


async def test_any_non_primary_id_falls_through_to_fallback() -> None:
    """정확히 일치하는 것만 primary다. 나머지는 전부 라우터가 만든 OpenRouter 후보다."""
    client, primary, fallback = build()

    await client.complete("google/gemini-3-flash-preview", "sys", "usr")

    assert primary.calls == []
    assert fallback.calls == ["google/gemini-3-flash-preview"]


async def test_closing_closes_both_underlying_clients() -> None:
    client, primary, fallback = build()

    await client.aclose()

    assert primary.closed is True
    assert fallback.closed is True
