from __future__ import annotations

from typing import Protocol

from common.models.user import User
from ..models.bookmark import Bookmark
from ..models.login_session import LoginSession


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
