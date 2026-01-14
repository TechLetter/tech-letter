from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from pymongo import IndexModel, ASCENDING

from common.models.identity_policy import PolicyKey
from .interfaces import IdentityPolicyRepositoryInterface


class IdentityPolicyRepository(IdentityPolicyRepositoryInterface):
    """identity_policies 컬렉션에 대한 MongoDB 접근 레이어."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._col = database["identity_policies"]
        # 인덱스 생성 (애플리케이션 시작 시 보장되어야 함)
        # identity_hash + policy_key 복합 유니크 인덱스
        self._col.create_indexes(
            [
                IndexModel(
                    [("identity_hash", ASCENDING), ("policy_key", ASCENDING)],
                    unique=True,
                    name="idx_identity_policy_unique",
                )
            ]
        )

    def try_use_policy(
        self, identity_hash: str, policy_key: PolicyKey, window_hours: int = 24
    ) -> bool:
        """정책 사용 시도 (Atomic)."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=window_hours)

        # 1. Update (이미 문서가 존재하는 경우 update)
        # last_acted_at이 cutoff보다 오래된 경우에만 업데이트
        # 문서가 없으면 match되지 않음 -> modified_count=0
        result = self._col.update_one(
            {
                "identity_hash": identity_hash,
                "policy_key": policy_key,
                "last_acted_at": {"$lt": cutoff},
            },
            {
                "$set": {
                    "last_acted_at": now,
                    "updated_at": now,
                }
            },
        )

        if result.modified_count == 1:
            return True

        # 2. Insert (문서가 아예 없는 경우)
        # 위 update에서 매칭되지 않았다면:
        # a) 문서가 아예 없거나
        # b) 최근에 이미 받음 (last_acted_at >= cutoff)

        # upsert=True를 쓰지 않고 분리하는 이유:
        # upsert=True 사용 시 조건($lt cutoff)이 안 맞으면(즉 이미 받음)
        # 새로운 문서를 insert 하려고 시도 -> Unique Index 에러 발생.
        # 이를 잡아서 처리해도 되지만, 명시적으로 insert 시도하는 게 직관적일 수 있음.
        # 다만 동시성 고려하면 upsert가 나을 수 있음.

        # 방식 변경: Upsert 활용
        try:
            # 쿼리 조건: "해시+키"가 일치하면서 "마지막 시간이 오래됨"
            # 만약 조건 불만족(최신) -> Match Fail -> Upsert 시도 ->
            #  -> $setOnInsert의 identity_hash, policy_key로 insert 시도 -> Unique Index 충돌!
            #  -> DuplicateKeyError 발생 -> return False

            # 만약 "문서 없음" -> Upsert 시도 -> Insert 성공 -> return True

            res_upsert = self._col.update_one(
                {
                    "identity_hash": identity_hash,
                    "policy_key": policy_key,
                    "last_acted_at": {"$lt": cutoff},
                },
                {
                    "$set": {
                        "last_acted_at": now,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "identity_hash": identity_hash,
                        "policy_key": policy_key,
                        "created_at": now,
                    },
                },
                upsert=True,
            )

            # upserted_id가 있으면 신규 생성 성공 -> True
            # modified_count가 1이면 기존 갱신 성공 -> True
            # 둘 다 아니면(0, None) -> 이미 최신 상태(매칭X, 인서트 중복실패X..가 아니라 인서트 실패는 예외로 빠짐)

            if res_upsert.upserted_id is not None or res_upsert.modified_count > 0:
                return True

            # 여기까지 왔다면:
            # match 되었으나 값 변경이 없음? (set 값과 같음) -> 시간 갱신이므로 그럴 일 없음.
            # match 안됨 -> upsert 시도 -> 근데 왜 예외 안남?
            # 아, find query에 있는 필드들이 $setOnInsert에 포함되지 않으면...
            # update_one의 첫번째 인자(filter)는 upsert 시 insert 되는 문서의 필드로 사용됨.
            # 단, 연산자($lt 등)가 포함된 필드는 제외됨.
            # 그래서 $setOnInsert에 명시적으로 PK를 넣어줬음.

            return False

        except DuplicateKeyError:
            # 이미 존재하며, 시간 조건($lt cutoff)을 만족하지 못해(최신이라) 매칭 실패 후
            # insert를 시도했으나 PK 충돌남 -> "이미 받음"
            return False
