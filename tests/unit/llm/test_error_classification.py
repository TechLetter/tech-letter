"""LLM 예외 분류 — ISSUE-001의 핵심.

현행은 모든 LLM 실패를 똑같이 다뤄 "일일 쿼터 소진"도 5회 재시도 후 DLQ로
보냈다. 실측 메시지로 회귀 테스트를 고정한다.
"""

from __future__ import annotations

import pytest

from techletter.core.errors import PermanentError, QuotaExceededError, RetryableError
from techletter.core.llm.errors import classify_llm_error, is_quota_error

# 운영 로그에서 그대로 가져온 문자열 (09 §6)
GEMINI_DAILY_QUOTA = (
    "ChatGoogleGenerativeAIError: Error calling model 'gemini-3-flash-preview' "
    "(RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
    "'message': 'You exceeded your current quota, please check your plan and billing "
    "details. Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 20'}}"
)
GEMINI_OVERLOADED = (
    "ServerError: 503 UNAVAILABLE. {'error': {'code': 503, 'message': "
    "'This model is currently experiencing high demand'}}"
)
OPENROUTER_RATE_LIMIT = (
    "RateLimitError: Error code: 429 - {'error': {'message': 'Provider returned error', "
    "'code': 429, 'metadata': {'raw': 'openai/gpt-oss-20b:free is temporarily "
    "rate-limited upstream. Please retry shortly'}}}"
)


def test_gemini_daily_quota_is_quota_not_rate_limit():
    """일일 한도 메시지에는 429가 함께 있다. 순서가 뒤바뀌면 분당 제한으로 오인한다."""
    assert is_quota_error(GEMINI_DAILY_QUOTA)
    assert isinstance(classify_llm_error(RuntimeError(GEMINI_DAILY_QUOTA)), QuotaExceededError)


def test_gemini_overloaded_is_retryable():
    assert isinstance(classify_llm_error(RuntimeError(GEMINI_OVERLOADED)), RetryableError)


def test_openrouter_rate_limit_is_retryable():
    result = classify_llm_error(RuntimeError(OPENROUTER_RATE_LIMIT))
    assert isinstance(result, RetryableError)
    assert not isinstance(result, QuotaExceededError)


@pytest.mark.parametrize(
    "message",
    [
        "AuthenticationError: 401 invalid_api_key",
        "NotFoundError: 404 model not found",
        "BadRequestError: 400 context length exceeded",
        "openai.NotFoundError: No endpoints found for openai/gpt-oss-20b:free",
    ],
)
def test_permanent_failures(message):
    assert isinstance(classify_llm_error(RuntimeError(message)), PermanentError)


@pytest.mark.parametrize(
    "message",
    [
        "ReadTimeout: request timed out",
        "APIConnectionError: connection reset by peer",
        "ServiceUnavailable: 502 bad gateway",
    ],
)
def test_transient_failures(message):
    assert isinstance(classify_llm_error(RuntimeError(message)), RetryableError)


def test_unknown_failure_defaults_to_retryable():
    """모르는 실패는 일단 재시도한다. 반복되면 max_attempt에서 걸린다."""
    result = classify_llm_error(RuntimeError("무슨 일이 일어난 건지 모르겠다"))
    assert isinstance(result, RetryableError)
    assert not isinstance(result, PermanentError)


def test_already_classified_errors_pass_through():
    original = QuotaExceededError("이미 분류됨")
    assert classify_llm_error(original) is original
