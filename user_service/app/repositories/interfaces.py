from __future__ import annotations

from typing import Protocol

from common.models.user import User


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
