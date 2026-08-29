"""에러 봉투와 코드 — 04 §1.3/§1.4가 원본이다."""

from __future__ import annotations

import pytest

from techletter.core import errors


@pytest.mark.parametrize(
    ("exc_type", "code", "status"),
    [
        (errors.InvalidRequestError, "request.invalid", 400),
        (errors.AuthRequiredError, "auth.required", 401),
        (errors.InvalidTokenError, "auth.invalid_token", 401),
        (errors.AuthForbiddenError, "auth.forbidden", 403),
        (errors.SessionExpiredError, "auth.session_expired", 400),
        (errors.ResourceNotFoundError, "resource.not_found", 404),
        (errors.ResourceConflictError, "resource.conflict", 409),
        (errors.InsufficientCreditsError, "credit.insufficient", 402),
        (errors.CreditError, "credit.error", 500),
        (errors.ChatSessionNotFoundError, "chat.session_not_found", 400),
        (errors.PolicyBlockedError, "policy.blocked", 403),
        (errors.LlmRateLimitedError, "llm.rate_limited", 429),
        (errors.LlmUnavailableError, "llm.unavailable", 503),
        (errors.InternalError, "internal.error", 500),
    ],
)
def test_error_code_and_status(exc_type, code, status):
    exc = exc_type()
    assert exc.code == code
    assert exc.status == status


def test_body_shape():
    body = errors.InsufficientCreditsError().to_body()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "credit.insufficient"
    assert body["error"]["message"]


def test_body_includes_details_when_present():
    body = errors.ResourceConflictError("이미 등록된 RSS입니다.", field="rss_url").to_body()
    assert body["error"]["details"] == {"field": "rss_url"}


def test_custom_message_overrides_default():
    assert errors.ResourceNotFoundError("포스트가 없습니다.").message == "포스트가 없습니다."


def test_job_errors_are_not_app_errors():
    """잡 실패는 HTTP 경계로 나가지 않는다. 잡 큐가 상태 전이에만 쓴다."""
    for exc_type in (errors.RetryableError, errors.PermanentError, errors.QuotaExceededError):
        assert not issubclass(exc_type, errors.AppError)
        assert issubclass(exc_type, errors.JobError)


def test_permanent_error_carries_reason():
    exc = errors.PermanentError("봇 차단 페이지", reason="bot_blocked")
    assert exc.reason == "bot_blocked"


def test_quota_error_carries_reset_at():
    from techletter.core.time import utcnow

    reset = utcnow()
    assert errors.QuotaExceededError("쿼터 소진", reset_at=reset).reset_at == reset
