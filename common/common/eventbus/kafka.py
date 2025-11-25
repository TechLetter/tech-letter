from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Callable

from confluent_kafka import Consumer, KafkaError, Producer

from .core import Event, MaxRetryExceededError, Topic, RetryDelays

logger = logging.getLogger(__name__)


class KafkaEventBus:
    """Kafka 기반 EventBus 구현.

    Go 구현(eventbus.KafkaEventBus)의 Subscribe 재시도/ DLQ 동작과 최대한 동일하게 맞춘다.
    """

    def __init__(self, brokers: str) -> None:
        self._producer = Producer({"bootstrap.servers": brokers})
        self._brokers = brokers

    def close(self) -> None:
        self._producer.flush()

    # 발행 -----------------------------------------------------------------
    def publish(self, topic: str, event: Event) -> None:
        payload = json.dumps(asdict(event), ensure_ascii=False).encode("utf-8")

        def _delivery_callback(err, msg) -> None:  # type: ignore[no-untyped-def]
            if err is not None:
                logger.error("failed to deliver message to %s: %s", msg.topic(), err)

        self._producer.produce(
            topic=topic,
            value=payload,
            key=event.id.encode("utf-8"),
            callback=_delivery_callback,
        )
        self._producer.poll(0)

    # 구독 -----------------------------------------------------------------
    def subscribe(
        self,
        group_id: str,
        topic: Topic,
        handler: Callable[[Event], None],
        *,
        poll_timeout: float = 0.1,
        stop_flag: list[bool] | None = None,
    ) -> None:
        consumer = Consumer(
            {
                "bootstrap.servers": self._brokers,
                "group.id": group_id,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe([topic.base])

        try:
            logger.info(
                "Kafka consumer started. group_id=%s topic=%s", group_id, topic.base
            )
            while True:
                if stop_flag and stop_flag[0]:
                    break

                msg = consumer.poll(poll_timeout)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("consumer error: %s", msg.error())
                    continue

                try:
                    raw = json.loads(msg.value())
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "invalid event payload on topic %s: %s", msg.topic(), exc
                    )
                    consumer.commit(message=msg, asynchronous=False)
                    continue

                evt = self._decode_event(raw)

                # MaxRetry 보정 (Go와 동일한 기본 동작)
                if evt.max_retry <= 0 or evt.max_retry > len(RetryDelays):
                    evt.max_retry = len(RetryDelays)

                try:
                    handler(evt)
                except Exception as exc:  # noqa: BLE001
                    # 핸들러 실패: 재시도 또는 DLQ
                    evt.last_error = str(exc)
                    next_retry = evt.retry + 1
                    try:
                        next_topic = topic.get_retry_topic(next_retry)
                    except MaxRetryExceededError:
                        logger.error(
                            "event %s exceeded max retry, sending to DLQ %s: %s",
                            evt.id,
                            topic.dlq(),
                            exc,
                        )
                        try:
                            self.publish(topic.dlq(), evt)
                        except Exception as pub_exc:  # noqa: BLE001
                            logger.error(
                                "failed to publish event %s to DLQ: %s", evt.id, pub_exc
                            )
                            continue  # 커밋하지 않음 -> 다시 처리 시도
                    else:
                        evt.retry = next_retry
                        logger.warning(
                            "event %s failed, scheduling retry %d/%d to %s",
                            evt.id,
                            evt.retry,
                            evt.max_retry,
                            next_topic,
                        )
                        try:
                            self.publish(next_topic, evt)
                        except Exception as pub_exc:  # noqa: BLE001
                            logger.error(
                                "failed to publish retry event %s to %s: %s",
                                evt.id,
                                next_topic,
                                pub_exc,
                            )
                            continue  # 커밋하지 않음 -> 다시 처리 시도

                # 성공 또는 재시도/DLQ 발행 성공 시 오프셋 커밋
                try:
                    consumer.commit(message=msg, asynchronous=False)
                except Exception as exc:  # noqa: BLE001
                    logger.error("offset commit error: %s", exc)
        finally:
            consumer.close()

    # 내부 util -------------------------------------------------------------
    @staticmethod
    def _decode_event(raw: dict) -> Event:
        return Event(
            id=str(raw.get("id", "")),
            payload=raw.get("payload"),
            retry=int(raw.get("retry", 0)),
            max_retry=int(raw.get("max_retry", 0)),
            last_error=raw.get("last_error"),
        )
