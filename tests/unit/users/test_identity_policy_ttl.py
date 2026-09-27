"""중복 지급 방지 기록의 보관 기간 — 개인정보처리방침과 같아야 한다."""

from __future__ import annotations

import techletter.users.repositories  # noqa: F401  # 인덱스 등록
from techletter.core.db.indexes import registered


def test_identity_policies_expire_after_three_days() -> None:
    specs = {spec.name: spec for spec in registered()["identity_policies"]}

    ttl = specs["ttl_identity_policy_last_acted"]
    assert ttl.keys == [("last_acted_at", 1)]
    assert ttl.expire_after_seconds == 3 * 24 * 3600
