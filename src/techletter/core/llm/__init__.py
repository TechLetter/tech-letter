"""LLM 접근 계층.

모든 LLM 호출은 `ModelRouter`를 거친다. 모델명을 코드나 설정에 박아두면
무료 모델이 사라질 때마다 배포가 필요해진다.
"""

from techletter.core.llm.budget import DailyBudget
from techletter.core.llm.errors import JsonOutputError, classify_llm_error
from techletter.core.llm.router import ModelRouter, truncate_for_model
from techletter.core.llm.scouter import ModelHealth, ScouterClient
from techletter.core.llm.stats import ModelPurpose, ModelStatsStore

__all__ = [
    "DailyBudget",
    "JsonOutputError",
    "ModelHealth",
    "ModelPurpose",
    "ModelRouter",
    "ModelStatsStore",
    "ScouterClient",
    "classify_llm_error",
    "truncate_for_model",
]
