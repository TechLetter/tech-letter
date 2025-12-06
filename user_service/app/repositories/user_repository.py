from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from common.models.user import User

from .documents.user_document import UserDocument
from .interfaces import UserRepositoryInterface


class UserRepository(UserRepositoryInterface):
    """users 컬렉션에 대한 MongoDB 접근 레이어."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["users"]

    @staticmethod
    def _from_document(doc: dict) -> User:
        document = UserDocument.model_validate(doc)
        return document.to_domain()

    def find_by_provider_and_sub(self, provider: str, provider_sub: str) -> User | None:
        doc = self._col.find_one({"provider": provider, "provider_sub": provider_sub})
        if not doc:
            return None
        return self._from_document(doc)

    def insert(self, user: User) -> User:
        now = datetime.now(timezone.utc)
        user.created_at = now
        user.updated_at = now

        document = UserDocument.from_domain(user)
        payload = document.to_mongo_record()
        self._col.insert_one(payload)
        return self._from_document(payload)

    def update_profile(
        self,
        user_code: str,
        email: str,
        name: str,
        profile_image: str,
    ) -> User:
        now = datetime.now(timezone.utc)
        result = self._col.find_one_and_update(
            {"user_code": user_code},
            {
                "$set": {
                    "email": email,
                    "name": name,
                    "profile_image": profile_image,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
        if not result:
            raise RuntimeError(f"user not found for update (user_code={user_code})")
        return self._from_document(result)

    def find_by_user_code(self, user_code: str) -> User | None:
        doc = self._col.find_one({"user_code": user_code})
        if not doc:
            return None
        return self._from_document(doc)
