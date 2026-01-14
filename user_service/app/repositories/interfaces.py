from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from common.models.user import User
from ..models.bookmark import Bookmark
from ..models.login_session import LoginSession

if TYPE_CHECKING:
    from ..models.credit import Credit, CreditSummary, CreditTransaction


class UserRepositoryInterface(Protocol):
    """UserRepository가 따라야 할 최소한의 계약.

    Service 레이어는 이 인터페이스에만 의존하고, 구체 구현(Mongo 등)은 몰라도 된다.
    """

    def find_by_provider_and_sub(
        self, provider: str, provider_sub: str
    ) -> User | None:  # pragma: no cover - Protocol
        ...

    def insert(self, user: User) -> User:  # pragma: no cover - Protocol
        ...

    def update_profile(
        self,
        user_code: str,
        email: str,
        name: str,
        profile_image: str,
    ) -> User:  # pragma: no cover - Protocol
        ...

    def find_by_user_code(
        self, user_code: str
    ) -> User | None:  # pragma: no cover - Protocol
        ...

    def delete_by_user_code(
        self, user_code: str
    ) -> bool:  # pragma: no cover - Protocol
        ...

    def list(
        self, page: int, page_size: int
    ) -> tuple[list[User], int]:  # pragma: no cover - Protocol
        ...


class BookmarkRepositoryInterface(Protocol):
    """BookmarkRepository가 따라야 할 최소한의 계약.

    - user_code + post_id 조합으로 유니크하게 북마크를 관리한다.
    """

    def create(
        self, user_code: str, post_id: str
    ) -> Bookmark:  # pragma: no cover - Protocol
        ...

    def delete(
        self, user_code: str, post_id: str
    ) -> bool:  # pragma: no cover - Protocol
        ...

    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[Bookmark], int]:  # pragma: no cover - Protocol
        ...

    def list_post_ids_for_user(
        self, user_code: str, post_ids: list[str]
    ) -> list[str]:  # pragma: no cover - Protocol
        ...

    def delete_all_by_user_code(
        self, user_code: str
    ) -> int:  # pragma: no cover - Protocol
        """주어진 user_code 의 모든 북마크를 삭제하고 삭제된 개수를 반환한다."""
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


class CreditTransactionRepositoryInterface(Protocol):
    """CreditTransactionRepository가 따라야 할 최소한의 계약."""

    def create(
        self, tx: "CreditTransaction"
    ) -> "CreditTransaction":  # pragma: no cover - Protocol
        ...

    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list["CreditTransaction"], int]:  # pragma: no cover - Protocol
        ...
