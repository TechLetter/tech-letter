"""크레딧 MongoDB 도큐먼트 (1:N 모델).

유저당 여러 크레딧 레코드를 저장하며, TTL 인덱스로 만료 시 자동 삭제된다.
"""

from __future__ import annotations

from datetime import datetime

from common.mongo.types import BaseDocument
from common.mongo.types import (
    MongoDateTime,
    from_object_id,
    build_document_data_from_domain,
)

from ...models.credit import Credit, CreditTransaction


class CreditDocument(BaseDocument):
    """MongoDB credits 컬렉션 도큐먼트 모델."""

    user_code: str
    amount: int
    original_amount: int
    source: str
    reason: str
    expired_at: MongoDateTime

    @classmethod
    def from_domain(cls, credit: Credit) -> "CreditDocument":
        data = build_document_data_from_domain(credit)
        return cls.model_validate(data)

    def to_domain(self) -> Credit:
        created_at: datetime = (
            self.created_at
            if isinstance(self.created_at, datetime)
            else datetime.fromisoformat(str(self.created_at))
        )
        expired_at: datetime = (
            self.expired_at
            if isinstance(self.expired_at, datetime)
            else datetime.fromisoformat(str(self.expired_at))
        )
        updated_at: datetime = (
            self.updated_at
            if isinstance(self.updated_at, datetime)
            else datetime.fromisoformat(str(self.updated_at))
        )
        return Credit(
            id=from_object_id(self.id),
            user_code=self.user_code,
            amount=self.amount,
            original_amount=self.original_amount,
            source=self.source,
            reason=self.reason,
            expired_at=expired_at,
            created_at=created_at,
            updated_at=updated_at,
        )


class CreditTransactionDocument(BaseDocument):
    """MongoDB credit_transactions 컬렉션 도큐먼트 모델."""

    user_code: str
    credit_id: str | None = None
    type: str
    amount: int
    reason: str
    metadata: dict | None = None

    @classmethod
    def from_domain(cls, tx: CreditTransaction) -> "CreditTransactionDocument":
        data = build_document_data_from_domain(tx)
        return cls.model_validate(data)

    def to_domain(self) -> CreditTransaction:
        created_at: datetime = (
            self.created_at
            if isinstance(self.created_at, datetime)
            else datetime.fromisoformat(str(self.created_at))
        )
        updated_at: datetime = (
            self.updated_at
            if isinstance(self.updated_at, datetime)
            else datetime.fromisoformat(str(self.updated_at))
        )
        return CreditTransaction(
            id=from_object_id(self.id),
            user_code=self.user_code,
            credit_id=self.credit_id,
            type=self.type,
            amount=self.amount,
            reason=self.reason,
            metadata=self.metadata,
            created_at=created_at,
            updated_at=updated_at,
        )
