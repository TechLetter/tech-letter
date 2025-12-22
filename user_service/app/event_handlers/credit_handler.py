"""크레딧 이벤트 핸들러.

Kafka에서 크레딧 관련 이벤트를 소비하여 트랜잭션 로그를 기록한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.database import Database

from common.eventbus.config import get_brokers, get_group_id
from common.eventbus.core import Event
from common.eventbus.kafka import KafkaEventBus
from common.eventbus.topics import TOPIC_CREDIT
from common.events.credit import (
    CreditEventType,
    CreditConsumedEvent,
    CreditGrantedEvent,
)

from ..repositories.credit_repository import CreditTransactionRepository
from ..models.credit import CreditTransaction


logger = logging.getLogger(__name__)


def _handle_credit_event(evt: Event, *, tx_repo: CreditTransactionRepository) -> None:
    """크레딧 이벤트를 처리하여 트랜잭션 로그를 기록한다."""
    payload = evt.payload
    if not isinstance(payload, dict):
        logger.error("unexpected payload type for event %s: %r", evt.id, type(payload))
        return

    event_type = str(payload.get("type", ""))

    if event_type == CreditEventType.CREDIT_CONSUMED:
        _handle_credit_consumed(payload, tx_repo)
    elif event_type == CreditEventType.CREDIT_GRANTED:
        _handle_credit_granted(payload, tx_repo)
    else:
        logger.debug("ignoring unknown credit event type=%s id=%s", event_type, evt.id)


def _handle_credit_consumed(
    payload: dict, tx_repo: CreditTransactionRepository
) -> None:
    """크레딧 소비 이벤트 처리."""
    try:
        event = CreditConsumedEvent.from_dict(payload)
    except Exception:
        logger.exception("failed to decode CreditConsumedEvent payload=%r", payload)
        raise

    logger.info(
        "handling credit.consumed event id=%s user_code=%s amount=%d",
        event.id,
        event.user_code,
        event.amount,
    )

    # 트랜잭션 로그 기록
    tx = CreditTransaction(
        user_code=event.user_code,
        credit_expired_at=datetime.fromisoformat(event.credit_expired_at),
        type="consume",
        amount=event.amount,
        reason=event.reason,
        metadata={
            "event_id": event.id,
            "session_id": event.session_id,
        },
        created_at=datetime.now(timezone.utc),
    )
    tx_repo.create(tx)
    logger.info("logged credit consume transaction for user_code=%s", event.user_code)


def _handle_credit_granted(payload: dict, tx_repo: CreditTransactionRepository) -> None:
    """크레딧 부여 이벤트 처리."""
    try:
        event = CreditGrantedEvent.from_dict(payload)
    except Exception:
        logger.exception("failed to decode CreditGrantedEvent payload=%r", payload)
        raise

    logger.info(
        "handling credit.granted event id=%s user_code=%s amount=%d",
        event.id,
        event.user_code,
        event.amount,
    )

    # 트랜잭션 로그 기록
    tx = CreditTransaction(
        user_code=event.user_code,
        credit_expired_at=datetime.fromisoformat(event.credit_expired_at),
        type="admin_grant",
        amount=event.amount,
        reason=event.reason,
        metadata={
            "event_id": event.id,
            "granted_by": event.granted_by,
        },
        created_at=datetime.now(timezone.utc),
    )
    tx_repo.create(tx)
    logger.info("logged credit grant transaction for user_code=%s", event.user_code)


def run_credit_consumer(stop_flag: list[bool], database: Database) -> None:
    """크레딧 이벤트를 소비하는 구독 루프를 실행한다."""
    logger.info("credit-consumer starting up")

    brokers = get_brokers()
    group_id = get_group_id() + "-credit"

    bus = KafkaEventBus(brokers)
    tx_repo = CreditTransactionRepository(database)

    try:
        logger.info("subscribing to topic=%s group_id=%s", TOPIC_CREDIT.base, group_id)
        bus.subscribe(
            group_id=group_id,
            topic=TOPIC_CREDIT,
            handler=lambda evt: _handle_credit_event(evt, tx_repo=tx_repo),
            stop_flag=stop_flag,
        )
    finally:
        bus.close()
        logger.info("credit-consumer stopped")
