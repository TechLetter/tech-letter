"""크레딧 레포지토리 구현체 (1:N 모델).

FIFO(만료 임박 순) 방식으로 크레딧을 소비하고, 집계 조회를 지원한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pymongo import IndexModel, ASCENDING
from pymongo.database import Database

from common.mongo.types import from_object_id, to_object_id

from .documents.credit_document import CreditDocument, CreditTransactionDocument
from .interfaces import CreditRepositoryInterface, CreditTransactionRepositoryInterface
from ..models.credit import Credit, CreditSummary, CreditTransaction


# 기본 일일 크레딧 수량
DEFAULT_DAILY_CREDITS = 10


class CreditRepository(CreditRepositoryInterface):
    """credits 컬렉션에 대한 MongoDB 접근 레이어 (1:N 모델)."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["credits"]
        self._col.create_indexes(
            [
                IndexModel(
                    [("expired_at", ASCENDING)],
                    name="ttl_expired_at",
                    expireAfterSeconds=0,
                ),
                IndexModel(
                    [("user_code", ASCENDING), ("expired_at", ASCENDING)],
                    name="idx_user_expired",
                ),
            ]
        )

    def get_summary(self, user_code: str) -> CreditSummary:
        """유저의 유효한 크레딧 합계 및 목록 조회 (FIFO 순)."""
        now = datetime.now(timezone.utc)
        cursor = self._col.find(
            {"user_code": user_code, "expired_at": {"$gt": now}, "amount": {"$gt": 0}},
            sort=[("expired_at", 1)],  # FIFO: 만료 임박 순
        )

        credits: list[Credit] = []
        total = 0
        for doc in cursor:
            credit = CreditDocument.model_validate(doc).to_domain()
            credits.append(credit)
            total += credit.amount

        return CreditSummary(
            user_code=user_code,
            total_remaining=total,
            credits=credits,
        )

    def get_summary_bulk(self, user_codes: list[str]) -> dict[str, int]:
        """여러 유저의 크레딧 잔액을 한 번에 조회 (N+1 방지)."""
        if not user_codes:
            return {}

        now = datetime.now(timezone.utc)
        pipeline = [
            {
                "$match": {
                    "user_code": {"$in": user_codes},
                    "expired_at": {"$gt": now},
                    "amount": {"$gt": 0},
                }
            },
            {"$group": {"_id": "$user_code", "total": {"$sum": "$amount"}}},
        ]

        result = {}
        for doc in self._col.aggregate(pipeline):
            result[doc["_id"]] = doc["total"]

        # 조회되지 않은 유저는 0으로 초기화
        for user_code in user_codes:
            if user_code not in result:
                result[user_code] = 0

        return result

    def delete_by_user(self, user_code: str) -> bool:
        """유저의 모든 크레딧 정보를 삭제."""
        result = self._col.delete_many({"user_code": user_code})
        # Note: 트랜잭션 로그는 보관할 수도 있지만, 개인정보 파기 원칙에 따라 삭제하는 것이 일반적
        # 여기서는 Credit 문서만 삭제 (트랜잭션 로그는 별도 컬렉션이라면 그것도 삭제 고려)
        return result.acknowledged

    def grant_daily(self, user_code: str) -> Credit | None:
        """일일 크레딧 지급. 오늘 이미 지급된 경우 None 반환."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_midnight = today_start + timedelta(days=1)

        # 오늘 이미 daily 크레딧이 있는지 확인
        existing = self._col.find_one(
            {
                "user_code": user_code,
                "source": "daily",
                "created_at": {"$gte": today_start},
            }
        )
        if existing:
            return None  # 이미 지급됨

        # 새 크레딧 생성
        new_doc = {
            "user_code": user_code,
            "amount": DEFAULT_DAILY_CREDITS,
            "original_amount": DEFAULT_DAILY_CREDITS,
            "source": "daily",
            "reason": "로그인 일일 지급",
            "expired_at": tomorrow_midnight,
            "created_at": now,
            "updated_at": now,
        }
        result = self._col.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id
        return CreditDocument.model_validate(new_doc).to_domain()

    def grant(
        self,
        user_code: str,
        amount: int,
        source: str,
        reason: str,
        expired_at: datetime,
    ) -> Credit:
        """크레딧 부여 (이벤트, 관리자 등)."""
        now = datetime.now(timezone.utc)
        new_doc = {
            "user_code": user_code,
            "amount": amount,
            "original_amount": amount,
            "source": source,
            "reason": reason,
            "expired_at": expired_at,
            "created_at": now,
            "updated_at": now,
        }
        result = self._col.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id
        return CreditDocument.model_validate(new_doc).to_domain()

    def consume(self, user_code: str, amount: int = 1) -> tuple[list[str], int] | None:
        """FIFO 방식으로 크레딧 차감.

        성공 시 (차감된 크레딧 ID 목록, 차감 후 총 잔액) 반환.
        잔액 부족 시 None 반환.
        """
        summary = self.get_summary(user_code)
        if summary.total_remaining < amount:
            return None  # 잔액 부족

        remaining_to_consume = amount
        consumed_credit_ids: list[str] = []
        now = datetime.now(timezone.utc)

        # FIFO: 만료 임박한 크레딧부터 차감
        for credit in summary.credits:
            if remaining_to_consume <= 0:
                break

            deduct = min(credit.amount, remaining_to_consume)
            self._col.update_one(
                {"_id": to_object_id(credit.id)},
                {
                    "$inc": {"amount": -deduct},
                    "$set": {"updated_at": now},
                },
            )
            remaining_to_consume -= deduct
            if credit.id:
                consumed_credit_ids.append(credit.id)

        # 차감 후 잔액 계산
        new_summary = self.get_summary(user_code)
        return consumed_credit_ids, new_summary.total_remaining

    def refund(self, credit_id: str, amount: int = 1) -> Credit | None:
        """특정 크레딧에 환불."""
        now = datetime.now(timezone.utc)
        from bson import ObjectId

        doc = self._col.find_one_and_update(
            {"_id": ObjectId(credit_id)},
            {
                "$inc": {"amount": amount},
                "$set": {"updated_at": now},
            },
            return_document=True,
        )
        if not doc:
            return None
        return CreditDocument.model_validate(doc).to_domain()


class CreditTransactionRepository(CreditTransactionRepositoryInterface):
    """credit_transactions 컬렉션에 대한 MongoDB 접근 레이어."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["credit_transactions"]

    def create(self, tx: CreditTransaction) -> CreditTransaction:
        """트랜잭션 로그 생성."""
        doc = CreditTransactionDocument.from_domain(tx)
        payload = doc.to_mongo_record()
        result = self._col.insert_one(payload)
        return CreditTransaction(
            id=str(result.inserted_id),
            user_code=tx.user_code,
            credit_id=tx.credit_id,
            type=tx.type,
            amount=tx.amount,
            reason=tx.reason,
            metadata=tx.metadata,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
        )

    def list_by_user(
        self, user_code: str, page: int, page_size: int
    ) -> tuple[list[CreditTransaction], int]:
        """사용자의 크레딧 트랜잭션 이력 조회."""
        if page <= 0:
            page = 1
        if page_size <= 0 or page_size > 100:
            page_size = 20

        skip = (page - 1) * page_size

        total = self._col.count_documents({"user_code": user_code})
        cursor = self._col.find(
            {"user_code": user_code},
            sort=[("created_at", -1), ("_id", -1)],
            skip=skip,
            limit=page_size,
        )

        items: list[CreditTransaction] = []
        for raw in cursor:
            items.append(CreditTransactionDocument.model_validate(raw).to_domain())

        return items, total
