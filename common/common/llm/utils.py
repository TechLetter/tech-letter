from __future__ import annotations


def normalize_model_name(model_name: str) -> str:
    """모델 이름을 정규화하여 저장소/캐시 식별자로 사용할 수 있게 한다.

    규칙:
    1. Provider Prefix 제거: '/'가 포함된 경우 마지막 부분만 사용한다.
       예: "google/gemini-embedding-001" -> "gemini-embedding-001"
       이유: OpenRouter 등 경유 시 prefix가 붙지만 모델 자체는 동일하므로 식별자를 통일한다.
    """
    if not model_name:
        return "unknown"

    # 1. Prefix 제거
    value = model_name.strip()
    if "/" in value:
        value = value.split("/")[-1].strip()
    return value or "unknown"
