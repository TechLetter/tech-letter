"""LLM 호출 클라이언트.

라우터(`ModelRouter`)는 "어떤 모델을 어떤 순서로 시도할지"만 정한다. 실제
호출은 여기서 한다.

무료 모델은 대부분 추론(reasoning) 모델이라 기본 설정으로 부르면 절반이
빈 응답을 준다 — 추론 토큰만 쓰고 `max_tokens`에 걸리기 때문이다.
ADR-0008 실측에서 나온 결론이라 `reasoning.exclude`와 넉넉한 `max_tokens`를
**기본값**으로 둔다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from techletter.core.llm.errors import JsonOutputError
from techletter.core.llm.stats import ModelPurpose
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.router import ModelRouter
    from techletter.settings import LlmSettings

__all__ = ["ChatClient", "LangChainChatClient", "LlmGateway", "extract_json"]

logger = get_logger(__name__)

DEFAULT_MAX_TOKENS = 8000
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def extract_json(raw: str) -> dict[str, Any]:
    """모델 응답에서 JSON 객체를 꺼낸다.

    ```json 펜스로 감싸거나 앞뒤에 설명을 붙이는 모델이 흔하다. 실패는
    `JsonOutputError`로 올려 라우터가 **다음 모델**로 넘어가게 한다.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise JsonOutputError(f"no json object in response: {raw[:200]!r}")
        cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise JsonOutputError(f"invalid json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise JsonOutputError("json response must be an object")
    return parsed


class ChatClient:
    """모델 하나를 호출하는 최소 인터페이스."""

    async def complete(
        self, model_id: str, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> str:  # pragma: no cover - 프로토콜
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover - 기본 no-op
        return


@dataclass(slots=True)
class _ModelKey:
    model_id: str
    max_tokens: int


class LangChainChatClient(ChatClient):
    """langchain 채팅 모델 래퍼. 모델 인스턴스를 재사용한다."""

    def __init__(self, settings: LlmSettings) -> None:
        self._settings = settings
        self._models: dict[tuple[str, int], Any] = {}

    def _build(self, model_id: str, max_tokens: int) -> Any:
        provider = self._settings.provider
        api_key = self._settings.api_key
        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

            return ChatGoogleGenerativeAI(
                model=model_id,
                temperature=self._settings.temperature,
                max_retries=self._settings.max_retries,
                max_output_tokens=max_tokens,
                timeout=self._settings.timeout_seconds,
                google_api_key=api_key,
            )

        from langchain_openai import ChatOpenAI  # noqa: PLC0415

        base_url = self._settings.base_url or (
            OPENROUTER_BASE_URL if provider == "openrouter" else None
        )
        extra: dict[str, Any] = {}
        if provider == "openrouter":
            # 추론 토큰을 응답에 포함하지 않는다. 켜 두면 max_tokens를 추론에
            # 다 쓰고 본문이 비어 나온다(ADR-0008 실측: 무료 모델 18개 전부 추론형).
            extra["reasoning"] = {"exclude": True}
        return ChatOpenAI(
            model=model_id,
            temperature=self._settings.temperature,
            base_url=base_url,
            api_key=api_key,
            max_retries=self._settings.max_retries,
            max_completion_tokens=max_tokens,
            timeout=self._settings.timeout_seconds,
            extra_body=extra or None,
        )

    def _get(self, model_id: str, max_tokens: int) -> Any:
        key = (model_id, max_tokens)
        if key not in self._models:
            self._models[key] = self._build(model_id, max_tokens)
        return self._models[key]

    async def complete(
        self, model_id: str, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

        response = await self._get(model_id, max_tokens).ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        usage = getattr(response, "usage_metadata", None) or {}
        if usage:
            # 토큰 폭주를 눈에 보이게 둔다(ADR-0008 §4).
            logger.debug(
                "llm usage",
                extra={"model_id": model_id, "output_tokens": usage.get("output_tokens")},
            )
        content = response.content
        if isinstance(content, list):
            # 일부 provider는 블록 배열을 준다.
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content).strip()


class LlmGateway:
    """라우터 + 클라이언트. 도메인 코드가 쓰는 진입점이다."""

    def __init__(self, router: ModelRouter, client: ChatClient) -> None:
        self._router = router
        self._client = client

    async def complete(
        self,
        purpose: ModelPurpose | str,
        system: str,
        user: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> tuple[str, str]:
        """텍스트 응답과 실제로 답한 모델 id를 준다."""
        target = ModelPurpose(purpose) if isinstance(purpose, str) else purpose
        return await self._router.run(
            target,
            lambda model_id: self._client.complete(model_id, system, user, max_tokens=max_tokens),
        )

    async def complete_json(
        self,
        purpose: ModelPurpose | str,
        system: str,
        user: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> tuple[dict[str, Any], str]:
        """JSON 객체를 요구한다. 파싱 실패는 그 모델의 실패로 친다.

        `extract_json`을 라우터 **안쪽**에서 부르는 것이 핵심이다. 그래야
        모양이 깨진 응답에서 다음 모델로 넘어간다.
        """
        target = ModelPurpose(purpose) if isinstance(purpose, str) else purpose

        async def call(model_id: str) -> dict[str, Any]:
            raw = await self._client.complete(model_id, system, user, max_tokens=max_tokens)
            return extract_json(raw)

        return await self._router.run(target, call)
