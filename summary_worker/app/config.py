from __future__ import annotations

import os
from dataclasses import dataclass

from common.llm.factory import ChatModelConfig, LlmProvider


SUMMARY_WORKER_LLM_PROVIDER = "SUMMARY_WORKER_LLM_PROVIDER"
SUMMARY_WORKER_LLM_MODEL_NAME = "SUMMARY_WORKER_LLM_MODEL_NAME"
SUMMARY_WORKER_LLM_API_KEY = "SUMMARY_WORKER_LLM_API_KEY"
SUMMARY_WORKER_LLM_TEMPERATURE = "SUMMARY_WORKER_LLM_TEMPERATURE"


@dataclass(slots=True)
class AppConfig:
    """summary-worker 전체 설정 루트.

    - 현재는 LLM 설정만 포함하지만, 추후 YAML 기반 설정 등이 추가될 수 있다.
    """

    llm: ChatModelConfig


def load_chat_model_config() -> ChatModelConfig:
    provider_raw = os.getenv(SUMMARY_WORKER_LLM_PROVIDER, "google")
    provider = LlmProvider.from_str(provider_raw)

    model = os.getenv(SUMMARY_WORKER_LLM_MODEL_NAME)
    if not model:
        raise RuntimeError(
            f"{SUMMARY_WORKER_LLM_MODEL_NAME} environment variable is required for summary-worker",
        )

    api_key = os.getenv(SUMMARY_WORKER_LLM_API_KEY) or None

    temperature_raw = os.getenv(SUMMARY_WORKER_LLM_TEMPERATURE)
    temperature = float(temperature_raw) if temperature_raw is not None else 0.3

    return ChatModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        api_key=api_key,
    )


def load_config() -> AppConfig:
    """summary-worker 설정을 로드하여 AppConfig 로 반환한다."""

    llm_config = load_chat_model_config()
    return AppConfig(llm=llm_config)
