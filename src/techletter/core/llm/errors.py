"""LLM provider 예외 → 잡 실패 종류 분류.

이 분류가 ISSUE-001의 핵심이다. 현행은 모든 LLM 실패를 똑같이 다뤄
"일일 쿼터 소진"도 5회 재시도 후 DLQ로 보냈다.

provider마다 예외 타입이 달라 **메시지 문자열**로 판별한다. 타입에 의존하면
langchain 래핑 방식이 바뀔 때마다 깨진다.
"""

from __future__ import annotations

import re

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError

__all__ = ["JsonOutputError", "classify_llm_error", "is_quota_error"]

# Gemini 무료 티어 일일 한도. 실측 메시지:
#   "Quota exceeded for metric: generativelanguage.googleapis.com/
#    generate_content_free_tier_requests, limit: 20"
_QUOTA_PATTERNS = [
    re.compile(r"resource[_ ]exhausted", re.I),
    re.compile(r"quota exceeded", re.I),
    re.compile(r"exceeded your current quota", re.I),
    re.compile(r"free_tier_requests", re.I),
    re.compile(r"daily limit", re.I),
    re.compile(r"insufficient[_ ]quota", re.I),
]

# 분당 제한·과부하처럼 곧 풀리는 것
_RETRYABLE_PATTERNS = [
    re.compile(r"\b429\b"),
    re.compile(r"rate.?limit", re.I),
    re.compile(r"too many requests", re.I),
    re.compile(r"\b(500|502|503|504)\b"),
    re.compile(r"unavailable", re.I),
    re.compile(r"overloaded", re.I),
    re.compile(r"high demand", re.I),
    re.compile(r"timeout|timed out", re.I),
    re.compile(r"connection (reset|error|aborted)", re.I),
    re.compile(r"temporarily", re.I),
]

# 재시도해도 같은 결과인 것
_PERMANENT_PATTERNS = [
    re.compile(r"\b40[0134]\b"),
    re.compile(r"invalid[_ ]api[_ ]key", re.I),
    re.compile(r"api key not valid", re.I),
    re.compile(r"unauthorized|forbidden", re.I),
    re.compile(r"model not found|does not exist|no endpoints found", re.I),
    re.compile(r"context length|too many tokens|maximum context", re.I),
    re.compile(r"safety|blocked by", re.I),
]


class JsonOutputError(Exception):
    """모델이 JSON 계약을 지키지 않았다. 같은 모델로 재시도하지 않고 다음 모델로 간다."""


def is_quota_error(message: str) -> bool:
    return any(p.search(message) for p in _QUOTA_PATTERNS)


def classify_llm_error(exc: BaseException) -> Exception:
    """provider 예외를 잡 큐가 이해하는 예외로 바꾼다.

    쿼터 판정을 rate limit보다 **먼저** 한다. Gemini의 일일 한도 메시지에는
    429와 RESOURCE_EXHAUSTED가 함께 들어 있어 순서가 뒤바뀌면 일일 한도를
    분당 제한으로 오인한다.
    """
    if isinstance(exc, QuotaExceededError | RetryableError | PermanentError):
        return exc

    message = f"{type(exc).__name__}: {exc}"

    if is_quota_error(message):
        return QuotaExceededError(message)
    if any(p.search(message) for p in _PERMANENT_PATTERNS):
        return PermanentError(message, reason="llm_permanent")
    if any(p.search(message) for p in _RETRYABLE_PATTERNS):
        return RetryableError(message)
    # 모르는 실패는 일단 재시도한다. 반복되면 max_attempt에서 걸린다.
    return RetryableError(message)
