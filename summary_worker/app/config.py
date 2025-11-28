from __future__ import annotations

import os

from common.llm.factory import ChatModelConfig, LlmProvider


SUMMARY_WORKER_LLM_PROVIDER = "SUMMARY_WORKER_LLM_PROVIDER"
SUMMARY_WORKER_LLM_MODEL_NAME = "SUMMARY_WORKER_LLM_MODEL_NAME"
SUMMARY_WORKER_LLM_API_KEY = "SUMMARY_WORKER_LLM_API_KEY"
SUMMARY_WORKER_LLM_TEMPERATURE = "SUMMARY_WORKER_LLM_TEMPERATURE"


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
