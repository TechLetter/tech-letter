"""users 도메인 저장소.

인덱스 **이름은 기존과 동일해야 한다**(05 §1.3). 이름이 다르면 운영 DB에
같은 키의 중복 인덱스가 생긴다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from techletter.core.db.indexes import IndexSpec, register_indexes
from techletter.core.pagination import Page
from techletter.core.time import utcnow
from techletter.users.models import (
    Bookmark,
    Credit,
    CreditSummary,
    CreditTransaction,
    LoginSession,
    User,
)

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime

    from bson import ObjectId
    from pymongo.asynchronous.database import AsyncDatabase

__all__ = [
    "BookmarkRepository",
    "CreditRepository",
    "CreditTransactionRepository",
    "IdentityPolicyRepository",
    "LoginSessionRepository",
    "UserRepository",
]

# ── 기존 인덱스 (이름 고정) ──────────────────────────────────────────
register_indexes(
    "users",
    [
        IndexSpec("uniq_user_code", [("user_code", ASCENDING)], unique=True),
        IndexSpec(
            "uniq_provider_provider_sub",
            [("provider", ASCENDING), ("provider_sub", ASCENDING)],
            unique=True,
        ),
    ],
)
register_indexes(
    "bookmarks",
    [
        IndexSpec(
            "uniq_user_code_post_id",
            [("user_code", ASCENDING), ("post_id", ASCENDING)],
            unique=True,
        ),
        IndexSpec(
            "idx_user_code_created_at_desc",
            [("user_code", ASCENDING), ("created_at", DESCENDING)],
        ),
    ],
)
register_indexes(
    "credits",
    [
        IndexSpec("ttl_expired_at", [("expired_at", ASCENDING)], expire_after_seconds=0),
        IndexSpec("idx_user_expired", [("user_code", ASCENDING), ("expired_at", ASCENDING)]),
    ],
)
register_indexes(
    "login_sessions",
    [
        IndexSpec("uniq_login_session_id", [("session_id", ASCENDING)], unique=True),
        IndexSpec(
            "ttl_login_session_expires_at",
            [("expires_at", ASCENDING)],
            expire_after_seconds=0,
        ),
    ],
)
register_indexes(
    "identity_policies",
    [
        IndexSpec(
            "idx_identity_policy_unique",
            [("identity_hash", ASCENDING), ("policy_key", ASCENDING)],
            unique=True,
        )
    ],
)
# ── 신규 인덱스 (05 §1.4) ────────────────────────────────────────────
register_indexes(
    "credit_transactions",
    [
        IndexSpec(
            "idx_credit_tx_user_created",
            [("user_code", ASCENDING), ("created_at", DESCENDING)],
        )
    ],
)


class UserRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["users"]

    async def get_by_user_code(self, user_code: str) -> User | None:
        doc = await self._col.find_one({"user_code": user_code})
        return User.model_validate(doc) if doc else None

    async def get_by_provider(self, provider: str, provider_sub: str) -> User | None:
        doc = await self._col.find_one({"provider": provider, "provider_sub": provider_sub})
        return User.model_validate(doc) if doc else None

    async def upsert(self, user: User) -> User:
        """provider+provider_sub 기준으로 생성하거나 프로필을 갱신한다."""
        now = utcnow()
        doc = await self._col.find_one_and_update(
            {"provider": user.provider, "provider_sub": user.provider_sub},
            {
                "$set": {
                    "email": user.email,
                    "name": user.name,
                    "profile_image": user.profile_image,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "user_code": user.user_code,
                    "provider": user.provider,
                    "provider_sub": user.provider_sub,
                    "role": user.role,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return User.model_validate(doc)

    async def list_users(self, page: Page) -> tuple[list[User], int]:
        total = await self._col.count_documents({})
        cursor = (
            self._col.find({})
            .sort([("created_at", DESCENDING)])
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [User.model_validate(doc) async for doc in cursor], total

    async def delete(self, user_code: str) -> bool:
        result = await self._col.delete_one({"user_code": user_code})
        return result.deleted_count > 0


class CreditRepository:
    """1:N 크레딧. FIFO(만료 임박 순)로 소비한다."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["credits"]

    async def summary(self, user_code: str) -> CreditSummary:
        now = utcnow()
        cursor = self._col.find(
            {"user_code": user_code, "expired_at": {"$gt": now}, "amount": {"$gt": 0}}
        ).sort([("expired_at", ASCENDING)])
        credits = [Credit.model_validate(doc) async for doc in cursor]
        return CreditSummary(
            user_code=user_code,
            total_remaining=sum(c.amount for c in credits),
            credits=credits,
        )

    async def remaining(self, user_code: str) -> int:
        pipeline = [
            {
                "$match": {
                    "user_code": user_code,
                    "expired_at": {"$gt": utcnow()},
                    "amount": {"$gt": 0},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        async for row in await self._col.aggregate(pipeline):
            return int(row["total"])
        return 0

    async def remaining_bulk(self, user_codes: list[str]) -> dict[str, int]:
        """어드민 유저 목록에서 N+1을 피하기 위한 벌크 조회."""
        if not user_codes:
            return {}
        pipeline = [
            {
                "$match": {
                    "user_code": {"$in": user_codes},
                    "expired_at": {"$gt": utcnow()},
                    "amount": {"$gt": 0},
                }
            },
            {"$group": {"_id": "$user_code", "total": {"$sum": "$amount"}}},
        ]
        result = dict.fromkeys(user_codes, 0)
        async for row in await self._col.aggregate(pipeline):
            result[row["_id"]] = int(row["total"])
        return result

    async def grant(
        self,
        user_code: str,
        amount: int,
        *,
        source: str,
        reason: str,
        expired_at: datetime,
    ) -> Credit:
        now = utcnow()
        credit = Credit(
            user_code=user_code,
            amount=amount,
            original_amount=amount,
            source=source,  # pyright: ignore[reportArgumentType]
            reason=reason,
            expired_at=expired_at,
            created_at=now,
            updated_at=now,
        )
        result = await self._col.insert_one(credit.to_mongo())
        credit.id = result.inserted_id
        return credit

    async def granted_today(self, user_code: str, source: str = "daily") -> bool:
        """오늘(UTC) 이미 같은 source로 지급됐는지. 현행 동작을 유지한다."""
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        doc = await self._col.find_one(
            {"user_code": user_code, "source": source, "created_at": {"$gte": today_start}},
            projection={"_id": 1},
        )
        return doc is not None

    async def take_one(self, user_code: str) -> ObjectId | None:
        """만료 임박 크레딧에서 1을 **원자적으로** 뺀다.

        현행은 조회 → 루프 `$inc` → 재조회라 동시 요청 시 잔액이 음수가 될 수
        있었다(ISSUE-012). 여기서는 `amount >= 1` 조건을 건 단일 연산이라
        경쟁이 나도 초과 차감이 생기지 않는다.
        """
        doc = await self._col.find_one_and_update(
            {"user_code": user_code, "expired_at": {"$gt": utcnow()}, "amount": {"$gte": 1}},
            {"$inc": {"amount": -1}, "$set": {"updated_at": utcnow()}},
            sort=[("expired_at", ASCENDING)],
            projection={"_id": 1},
            return_document=ReturnDocument.AFTER,
        )
        return doc["_id"] if doc else None

    async def give_back(self, credit_id: ObjectId | str, amount: int = 1) -> bool:
        """환불. `original_amount`를 넘지 않는 선에서만 되돌린다.

        현행 `refund`는 상한이 없어 중복 환불이 잔액을 부풀릴 수 있었다.
        """
        from bson import ObjectId as Oid  # noqa: PLC0415

        oid = credit_id if not isinstance(credit_id, str) else Oid(credit_id)
        result = await self._col.update_one(
            {
                "_id": oid,
                "$expr": {"$lte": [{"$add": ["$amount", amount]}, "$original_amount"]},
            },
            {"$inc": {"amount": amount}, "$set": {"updated_at": utcnow()}},
        )
        return result.modified_count > 0

    async def delete_by_user(self, user_code: str) -> int:
        result = await self._col.delete_many({"user_code": user_code})
        return result.deleted_count


class CreditTransactionRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["credit_transactions"]

    async def create(self, transaction: CreditTransaction) -> CreditTransaction:
        result = await self._col.insert_one(transaction.to_mongo())
        transaction.id = result.inserted_id
        return transaction

    async def list_by_user(self, user_code: str, page: Page) -> tuple[list[CreditTransaction], int]:
        query = {"user_code": user_code}
        total = await self._col.count_documents(query)
        cursor = (
            self._col.find(query)
            .sort([("created_at", DESCENDING)])
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [CreditTransaction.model_validate(doc) async for doc in cursor], total

    async def delete_by_user(self, user_code: str) -> int:
        result = await self._col.delete_many({"user_code": user_code})
        return result.deleted_count


class BookmarkRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["bookmarks"]

    async def add(self, user_code: str, post_id: str) -> Bookmark:
        now = utcnow()
        doc = await self._col.find_one_and_update(
            {"user_code": user_code, "post_id": post_id},
            {"$setOnInsert": {"created_at": now}, "$set": {"updated_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return Bookmark.model_validate(doc)

    async def remove(self, user_code: str, post_id: str) -> bool:
        result = await self._col.delete_one({"user_code": user_code, "post_id": post_id})
        return result.deleted_count > 0

    async def list_post_ids(self, user_code: str, page: Page) -> tuple[list[str], int]:
        query = {"user_code": user_code}
        total = await self._col.count_documents(query)
        cursor = (
            self._col.find(query, projection={"post_id": 1})
            .sort([("created_at", DESCENDING)])
            .skip(page.skip)
            .limit(page.page_size)
        )
        return [doc["post_id"] async for doc in cursor], total

    async def filter_bookmarked(self, user_code: str, post_ids: list[str]) -> set[str]:
        """주어진 포스트 중 북마크된 것만. 목록 응답의 `is_bookmarked` 계산용."""
        if not post_ids:
            return set()
        cursor = self._col.find(
            {"user_code": user_code, "post_id": {"$in": post_ids}}, projection={"post_id": 1}
        )
        return {doc["post_id"] async for doc in cursor}

    async def delete_by_user(self, user_code: str) -> int:
        result = await self._col.delete_many({"user_code": user_code})
        return result.deleted_count


class LoginSessionRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["login_sessions"]

    async def create(self, session_id: str, jwt_token: str, ttl_seconds: int) -> LoginSession:
        now = utcnow()
        session = LoginSession(
            session_id=session_id,
            jwt_token=jwt_token,
            expires_at=now + timedelta(seconds=ttl_seconds),
            created_at=now,
            updated_at=now,
        )
        result = await self._col.insert_one(session.to_mongo())
        session.id = result.inserted_id
        return session

    async def consume(self, session_id: str) -> str | None:
        """1회용 교환. 원자적으로 꺼내고 지운다."""
        doc = await self._col.find_one_and_delete({"session_id": session_id})
        if not doc:
            return None
        expires_at = doc.get("expires_at")
        # TTL 인덱스는 최대 60초 지연될 수 있으므로 만료를 직접 확인한다.
        if expires_at is not None and expires_at <= utcnow():
            return None
        return doc.get("jwt_token")


class IdentityPolicyRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._col = db["identity_policies"]

    async def try_use(self, identity_hash: str, policy_key: str, *, window_hours: int = 24) -> bool:
        """정책을 소비한다. 창 안에 이미 사용했으면 False.

        "오래된 것 갱신 → 없으면 삽입" 두 단계다.

        **`idx_identity_policy_unique`(유니크)에 의존한다.** 인덱스가 없으면
        동시 삽입이 모두 성공해 중복 지급이 조용히 일어난다. 부팅 시
        `ensure_indexes()`가 반드시 실행되어야 한다.
        """
        now = utcnow()
        cutoff = now - timedelta(hours=window_hours)
        result = await self._col.update_one(
            {
                "identity_hash": identity_hash,
                "policy_key": policy_key,
                "last_acted_at": {"$lt": cutoff},
            },
            {"$set": {"last_acted_at": now, "updated_at": now}},
        )
        if result.modified_count == 1:
            return True

        try:
            await self._col.insert_one(
                {
                    "identity_hash": identity_hash,
                    "policy_key": policy_key,
                    "last_acted_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except DuplicateKeyError:
            # 문서는 있는데 창 안에 이미 사용했다.
            return False
        return True

    async def raw(self, identity_hash: str, policy_key: str) -> dict[str, Any] | None:
        return await self._col.find_one({"identity_hash": identity_hash, "policy_key": policy_key})
