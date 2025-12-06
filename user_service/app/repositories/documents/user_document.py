from __future__ import annotations

from datetime import datetime

from common.models.user import User
from common.mongo.types import BaseDocument, build_document_data_from_domain


class UserDocument(BaseDocument):
    """MongoDB users 컬렉션 도큐먼트 모델."""

    user_code: str
    provider: str
    provider_sub: str
    email: str
    name: str
    profile_image: str
    role: str

    @classmethod
    def from_domain(cls, user: User) -> "UserDocument":
        data = build_document_data_from_domain(user)
        # User 도메인 모델에는 _id 를 노출하지 않으므로 단순 검증만 수행한다.
        return cls.model_validate(data)

    def to_domain(self) -> User:
        return User(
            user_code=self.user_code,
            provider=self.provider,
            provider_sub=self.provider_sub,
            email=self.email,
            name=self.name,
            profile_image=self.profile_image,
            role=self.role,
            created_at=(
                self.created_at
                if isinstance(self.created_at, datetime)
                else datetime.fromisoformat(str(self.created_at))
            ),
            updated_at=(
                self.updated_at
                if isinstance(self.updated_at, datetime)
                else datetime.fromisoformat(str(self.updated_at))
            ),
        )
