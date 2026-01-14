from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from abc import abstractmethod

from common.models.user import User
from ..models.bookmark import Bookmark
from ..models.login_session import LoginSession

if TYPE_CHECKING:
    from ..models.credit import Credit, CreditSummary, CreditTransaction
    from app.models.chat_session import ChatMessage, ChatSession
    from common.models.identity_policy import PolicyKey


@runtime_checkable
class IdentityPolicyRepositoryInterface(Protocol):
    """IdentityPolicyRepository가 따라야 할 최소한의 계약."""

    @abstractmethod
    def try_use_policy(
        self, identity_hash: str, policy_key: PolicyKey, window_hours: int = 24
    ) -> bool:
        """정책 사용 시도 (Atomic).

        해당 identity+policy에 대해 window 시간 내에 사용 이력이 없으면
        현재 시간으로 갱신하고 True를 반환한다.
        이미 사용 이력이 있으면 False를 반환한다.
        """
        ...


@runtime_checkable
class UserRepositoryInterface(Protocol):
    """UserRepository가 따라야 할 최소한의 계약.

    User Service 비즈니스 로직은 오직 이 인터페이스에만 의존한다.
    """

    @abstractmethod
    def insert(self, user: User) -> User: ...

    @abstractmethod
    def update_profile(
        self,
        user_code: str,
        email: str | None = None,
        name: str | None = None,
        profile_image: str | None = None,
    ) -> User: ...

    @abstractmethod
    def find_by_user_code(self, user_code: str) -> User | None: ...

    @abstractmethod
    def find_by_provider_and_sub(
        self, provider: str, provider_sub: str
    ) -> User | None: ...

    @abstractmethod
    def list(self, page: int, page_size: int) -> tuple[list[User], int]: ...

    @abstractmethod
    def delete(self, user_code: str) -> bool: ...


@runtime_checkable
class BookmarkRepositoryInterface(Protocol):
    """BookmarkRepository가 따라야 할 최소한의 계약.

    User Service 비즈니스 로직은 오직 이 인터페이스에만 의존한다.
    """

    @abstractmethod
    def create(self, user_code: str, post_id: str) -> Bookmark:
        """북마크 생성 (upsert)."""
        ...

    @abstractmethod
    def delete(self, user_code: str, post_id: str) -> bool:
        """북마크 삭제."""
        ...

    @abstractmethod
    def exists(self, user_code: str, post_id: str) -> bool:
        """북마크 존재 여부 확인."""
        ...

    @abstractmethod
    def delete_by_user(self, user_code: str) -> bool:
        """유저의 모든 북마크 삭제."""
        ...

    @abstractmethod
    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[Bookmark], int]:
        """북마크 목록과 총 개수 반환."""
        ...

    @abstractmethod
    def list_post_ids_for_user(self, user_code: str, post_ids: list[str]) -> list[str]:
        """주어진 post_ids 중 유저가 북마크한 것들만 반환."""
        ...

    @abstractmethod
    def delete_all_by_user_code(self, user_code: str) -> int:
        """주어진 user_code의 모든 북마크를 삭제하고 삭제된 개수 반환."""
        ...


class LoginSessionRepositoryInterface(Protocol):
    """LoginSessionRepository가 따라야 할 최소한의 계약.

    - 세션은 한 번만 사용 가능하며, session_id 로 삭제/조회한다.
    """

    def create(
        self, session: LoginSession
    ) -> LoginSession:  # pragma: no cover - Protocol
        ...

    def delete_by_session_id(
        self, session_id: str
    ) -> LoginSession | None:  # pragma: no cover - Protocol
        ...


class CreditRepositoryInterface(Protocol):
    """CreditRepository가 따라야 할 최소한의 계약 (1:N 모델).

    - 크레딧 집계 조회, FIFO 차감, 일일 지급, 환불을 처리한다.
    """

    def get_summary(
        self, user_code: str
    ) -> CreditSummary:  # pragma: no cover - Protocol
        """유저의 유효한 크레딧 합계 및 목록 조회."""
        ...

    def get_summary_bulk(
        self, user_codes: list[str]
    ) -> dict[str, int]:  # pragma: no cover - Protocol
        """여러 유저의 크레딧 잔액을 벌크 조회 (N+1 방지)."""
        ...

    def grant_daily(
        self, user_code: str
    ) -> "Credit | None":  # pragma: no cover - Protocol
        """일일 크레딧 지급. 이미 지급된 경우 None."""
        ...

    def grant(
        self,
        user_code: str,
        amount: int,
        source: str,
        reason: str,
        expired_at: "datetime",
    ) -> "Credit":  # pragma: no cover - Protocol
        """크레딧 부여 (이벤트, 관리자 등)."""
        ...

    def consume(
        self, user_code: str, amount: int
    ) -> tuple[list[str], int] | None:  # pragma: no cover - Protocol
        """FIFO 크레딧 차감. 성공 시 (차감된 크레딧 ID 목록, 잔액) 반환, 실패 시 None."""
        ...

    def refund(
        self, credit_id: str, amount: int
    ) -> "Credit | None":  # pragma: no cover - Protocol
        """특정 크레딧에 환불."""
        ...

    def delete_by_user(self, user_code: str) -> bool:
        """유저의 모든 크레딧 삭제."""
        ...


@runtime_checkable
class CreditTransactionRepositoryInterface(Protocol):
    """CreditTransactionRepository가 따라야 할 최소한의 계약."""

    @abstractmethod
    def create(self, tx: "CreditTransaction") -> "CreditTransaction": ...

    @abstractmethod
    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list["CreditTransaction"], int]: ...


@runtime_checkable
class ChatSessionRepositoryInterface(Protocol):
    """ChatSessionRepository가 따라야 할 최소한의 계약."""

    @abstractmethod
    def create(self, session: "ChatSession") -> "ChatSession": ...

    @abstractmethod
    def get_by_id(self, session_id: str, user_code: str) -> "ChatSession | None": ...

    @abstractmethod
    def list_sessions(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list["ChatSession"], int]: ...

    @abstractmethod
    def add_message(
        self, session_id: str, message: "ChatMessage"
    ) -> "ChatSession | None": ...

    @abstractmethod
    def get_by_id_only(self, session_id: str) -> "ChatSession | None": ...

    @abstractmethod
    def update_title(self, session_id: str, title: str) -> "ChatSession | None": ...

    @abstractmethod
    def delete(self, session_id: str, user_code: str) -> bool: ...

    @abstractmethod
    def delete_by_user(self, user_code: str) -> bool: ...
