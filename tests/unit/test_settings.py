"""LLM API 키 — provider당 계정 하나(GEMINI_API_KEY/OPENROUTER_API_KEY)를 공유한다."""

from __future__ import annotations

from techletter.settings import (
    ChatEmbeddingSettings,
    ChatLlmSettings,
    EmbeddingLlmSettings,
    SummaryLlmSettings,
)


def test_summary_llm_falls_back_to_shared_gemini_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini")
    settings = SummaryLlmSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "shared-gemini"


def test_embedding_llm_falls_back_to_shared_gemini_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini")
    settings = EmbeddingLlmSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "shared-gemini"


def test_chat_embedding_falls_back_to_shared_gemini_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini")
    settings = ChatEmbeddingSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "shared-gemini"


def test_chat_llm_falls_back_to_shared_openrouter_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "shared-openrouter")
    settings = ChatLlmSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "shared-openrouter"


def test_role_specific_env_var_has_no_effect(monkeypatch) -> None:
    """`EMBEDDING_WORKER_LLM_API_KEY` 같은 옛 역할별 변수는 이제 그냥 무시된다.

    api_key가 pydantic 필드가 아니라 PrivateAttr인 이유가 바로 이거다 —
    필드였다면 `populate_by_name`이 필드명(+env_prefix)으로도 채우려 들어서
    이 옛 변수가 여전히 새어 들어왔을 것이다.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "shared-gemini")
    monkeypatch.setenv("EMBEDDING_WORKER_LLM_API_KEY", "should-be-ignored")

    settings = EmbeddingLlmSettings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "shared-gemini"


def test_no_key_configured_is_none(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SUMMARY_WORKER_LLM_API_KEY", raising=False)
    # 로컬 `.env` 파일이 있어도 이 테스트에는 안 섞이게 한다.
    settings = SummaryLlmSettings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.api_key is None
