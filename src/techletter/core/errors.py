"""애플리케이션 예외 계층.

두 축이 있다.

1. `AppError` — HTTP 경계로 나가는 도메인 오류. 에러 코드와 상태 코드를 가진다.
2. `JobError` — 잡 처리 실패의 성격 분류. 잡 큐가 재시도/영구실패/쿼터대기를
   구분하는 데 쓴다.

도메인 코드는 `HTTPException`을 직접 던지지 않는다. api 레이어가 변환한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

__all__ = [
    "AppError",
    "AuthForbiddenError",
    "AuthRequiredError",
    "ChatSessionNotFoundError",
    "CreditError",
    "InsufficientCreditsError",
    "InternalError",
    "InvalidRequestError",
    "InvalidTokenError",
    "JobError",
    "LlmRateLimitedError",
    "LlmUnavailableError",
    "PermanentError",
    "PolicyBlockedError",
    "QuotaExceededError",
    "ResourceConflictError",
    "ResourceNotFoundError",
    "RetryableError",
    "SessionExpiredError",
]


class AppError(Exception):
    """HTTP로 나가는 도메인 오류의 기반 클래스."""

    code: str = "internal.error"
    status: int = 500
    default_message: str = "일시적인 오류가 발생했습니다."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_body(self) -> dict[str, Any]:
        """에러 봉투로 직렬화한다."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


class InvalidRequestError(AppError):
    code = "request.invalid"
    status = 400
    default_message = "요청 형식이 올바르지 않습니다."


class AuthRequiredError(AppError):
    code = "auth.required"
    status = 401
    default_message = "로그인이 필요합니다."


class InvalidTokenError(AppError):
    code = "auth.invalid_token"
    status = 401
    default_message = "인증 정보가 만료되었거나 올바르지 않습니다."


class AuthForbiddenError(AppError):
    code = "auth.forbidden"
    status = 403
    default_message = "접근 권한이 없습니다."


class SessionExpiredError(AppError):
    code = "auth.session_expired"
    status = 400
    default_message = "로그인 세션이 만료되었거나 유효하지 않습니다."


class ResourceNotFoundError(AppError):
    code = "resource.not_found"
    status = 404
    default_message = "대상을 찾을 수 없습니다."


class ResourceConflictError(AppError):
    code = "resource.conflict"
    status = 409
    default_message = "이미 존재하는 값입니다."

    def __init__(self, message: str | None = None, *, field: str | None = None) -> None:
        super().__init__(message, details={"field": field} if field else None)


class InsufficientCreditsError(AppError):
    code = "credit.insufficient"
    status = 402
    default_message = "크레딧이 부족합니다. 내일 다시 시도해 주세요."


class CreditError(AppError):
    code = "credit.error"
    status = 500
    default_message = "크레딧 처리 중 오류가 발생했습니다."


class ChatSessionNotFoundError(AppError):
    code = "chat.session_not_found"
    status = 400
    default_message = "세션을 찾을 수 없습니다. 새 채팅을 시작해 주세요."


class PolicyBlockedError(AppError):
    code = "policy.blocked"
    status = 403
    default_message = (
        "요청에 내부 지시 변경 또는 민감 정보 요청으로 해석될 수 있는 내용이 포함되어 "
        "처리하지 않았습니다."
    )


class LlmRateLimitedError(AppError):
    code = "llm.rate_limited"
    status = 429
    default_message = "AI API 호출이 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요."


class LlmUnavailableError(AppError):
    code = "llm.unavailable"
    status = 503
    default_message = "AI 서버가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요."


class InternalError(AppError):
    code = "internal.error"
    status = 500


# ── 잡 처리 실패 분류 ────────────────────────────────────────────────


class JobError(Exception):
    """잡 핸들러가 던지는 실패. 잡 큐가 이 종류를 보고 다음 상태를 정한다."""


class RetryableError(JobError):
    """일시적 실패. 백오프 후 재시도한다."""


class PermanentError(JobError):
    """재시도해도 성공할 수 없는 실패. 즉시 dead 처리한다."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(message)


class QuotaExceededError(JobError):
    """일일 쿼터 소진. 리셋 시각까지 대기하며 attempt를 소모하지 않는다."""

    def __init__(self, message: str, *, reset_at: datetime | None = None) -> None:
        self.reset_at = reset_at
        super().__init__(message)
