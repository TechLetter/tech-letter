from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class PolicyKey(StrEnum):
    DAILY_CREDIT_GRANT = "DAILY_CREDIT_GRANT"
    # WELCOME_BONUS = "WELCOME_BONUS"  # 예시
    # EVENT_PARTICIPATION = "EVENT_PARTICIPATION"  # 예시


@dataclass
class IdentityPolicy:
    identity_hash: str
    policy_key: PolicyKey
    last_acted_at: datetime
    payload: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
