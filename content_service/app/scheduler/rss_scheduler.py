from __future__ import annotations

import logging
import threading

from common.eventbus.config import get_brokers
from common.eventbus.kafka import KafkaEventBus
from common.mongo.client import get_database

from ..config import load_config
from ..repositories.blog_repository import BlogRepository
from ..repositories.post_repository import PostRepository
from ..services.aggregate_service import AggregateService


logger = logging.getLogger(__name__)


_RSS_SCHEDULER_THREAD: threading.Thread | None = None
_RSS_SCHEDULER_STOP_EVENT: threading.Event | None = None

# Go Aggregate 의 RSSFeedCollectionInterval 과 동일한 30분 주기.
RSS_SCHEDULER_INTERVAL_SECONDS = 30.0 * 60.0


def _run_scheduler_loop(stop_event: threading.Event) -> None:
    logger.info(
        "RSS scheduler thread started (interval=%.0f seconds)",
        RSS_SCHEDULER_INTERVAL_SECONDS,
    )

    db = get_database()
    blog_repo = BlogRepository(db)
    post_repo = PostRepository(db)

    brokers = get_brokers()
    bus = KafkaEventBus(brokers)

    service = AggregateService(
        blog_repository=blog_repo,
        post_repository=post_repo,
        event_bus=bus,
        source="content-service",
    )

    try:
        interval = RSS_SCHEDULER_INTERVAL_SECONDS

        # 최초 실행
        logger.info("RSS feed collection starting (initial run)")
        try:
            cfg = load_config().aggregate
            service.run_feed_collection(cfg)
            logger.info("RSS feed collection completed (initial run)")
        except Exception:  # noqa: BLE001
            logger.exception("RSS feed collection failed (initial run)")

        # 주기적 실행
        while not stop_event.wait(interval):
            logger.info("RSS feed collection starting (scheduled run)")
            try:
                cfg = load_config().aggregate
                service.run_feed_collection(cfg)
                logger.info("RSS feed collection completed (scheduled run)")
            except Exception:  # noqa: BLE001
                logger.exception("RSS feed collection failed (scheduled run)")
    finally:
        bus.close()
        logger.info("RSS scheduler thread stopped")


def start_rss_scheduler() -> None:
    """RSS 수집 스케줄러 스레드를 시작한다.

    FastAPI startup 이벤트에서 호출된다.
    """

    global _RSS_SCHEDULER_THREAD, _RSS_SCHEDULER_STOP_EVENT

    if _RSS_SCHEDULER_THREAD and _RSS_SCHEDULER_THREAD.is_alive():
        return

    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_scheduler_loop,
        args=(stop_event,),
        name="rss-scheduler",
        daemon=True,
    )

    _RSS_SCHEDULER_STOP_EVENT = stop_event
    _RSS_SCHEDULER_THREAD = thread

    thread.start()
    logger.info("RSS scheduler thread launched")


def stop_rss_scheduler() -> None:
    """RSS 수집 스케줄러 스레드를 정지한다.

    FastAPI shutdown 이벤트에서 호출된다.
    """

    global _RSS_SCHEDULER_THREAD, _RSS_SCHEDULER_STOP_EVENT

    if _RSS_SCHEDULER_THREAD is None or _RSS_SCHEDULER_STOP_EVENT is None:
        return

    _RSS_SCHEDULER_STOP_EVENT.set()
    _RSS_SCHEDULER_THREAD.join(timeout=10.0)

    _RSS_SCHEDULER_THREAD = None
    _RSS_SCHEDULER_STOP_EVENT = None

    logger.info("RSS scheduler thread stopped by shutdown")
