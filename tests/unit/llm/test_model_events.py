"""모델 카탈로그 변동 감지 — 순수 diff 로직."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from techletter.core.llm.model_events import EventType, _CatalogEntry, _diff
from techletter.core.llm.model_scan import ModelCheck

NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
EARLIER = NOW - timedelta(days=3)


def _check(model_id: str, *, ok: bool, category: str | None = None) -> ModelCheck:
    return ModelCheck(
        model_id=model_id,
        ok=ok,
        http_status=None if ok else 429,
        latency_ms=100 if ok else None,
        error_category=category,
        checked_at=NOW,
    )


def _entry(
    model_id: str, *, is_active=True, consecutive_failures=0, degraded=False
) -> _CatalogEntry:
    return _CatalogEntry(
        model_id=model_id,
        is_active=is_active,
        consecutive_failures=consecutive_failures,
        degraded=degraded,
        first_seen_at=EARLIER,
        last_seen_at=EARLIER,
    )


def _types(events: list[dict]) -> set[str]:
    return {e["type"] for e in events}


def test_a_model_never_seen_before_is_added():
    events, updates = _diff({}, [_check("a/free", ok=True)], degrade_threshold=2, now=NOW)

    assert _types(events) == {EventType.MODEL_ADDED.value}
    assert updates["a/free"]["is_active"] is True
    assert updates["a/free"]["first_seen_at"] == NOW


def test_a_healthy_model_produces_no_event():
    previous = {"a/free": _entry("a/free")}
    events, updates = _diff(previous, [_check("a/free", ok=True)], degrade_threshold=2, now=NOW)

    assert events == []
    assert updates["a/free"]["consecutive_failures"] == 0
    assert updates["a/free"]["degraded"] is False


def test_a_single_failure_does_not_degrade_below_threshold():
    """단발성 blip으로 매시간 저하/복구가 반복되면 안 된다."""
    previous = {"a/free": _entry("a/free", consecutive_failures=0)}
    events, updates = _diff(previous, [_check("a/free", ok=False)], degrade_threshold=2, now=NOW)

    assert events == []
    assert updates["a/free"]["consecutive_failures"] == 1
    assert updates["a/free"]["degraded"] is False


def test_reaching_the_threshold_emits_degraded_with_a_reason():
    previous = {"a/free": _entry("a/free", consecutive_failures=1)}
    events, updates = _diff(
        previous,
        [_check("a/free", ok=False, category="rate_limited")],
        degrade_threshold=2,
        now=NOW,
    )

    assert _types(events) == {EventType.MODEL_DEGRADED.value}
    assert events[0]["reason"] == "rate_limited"
    assert updates["a/free"]["degraded"] is True


def test_degraded_does_not_fire_again_while_still_failing():
    """이미 저하 상태면 계속 실패해도 이벤트를 또 내지 않는다."""
    previous = {"a/free": _entry("a/free", consecutive_failures=5, degraded=True)}
    events, _ = _diff(previous, [_check("a/free", ok=False)], degrade_threshold=2, now=NOW)

    assert events == []


def test_recovery_after_degraded_emits_recovered():
    previous = {"a/free": _entry("a/free", consecutive_failures=3, degraded=True)}
    events, updates = _diff(previous, [_check("a/free", ok=True)], degrade_threshold=2, now=NOW)

    assert _types(events) == {EventType.MODEL_RECOVERED.value}
    assert updates["a/free"]["consecutive_failures"] == 0
    assert updates["a/free"]["degraded"] is False


def test_a_model_missing_from_the_scan_is_removed():
    previous = {"a/free": _entry("a/free"), "b/free": _entry("b/free")}
    events, updates = _diff(previous, [_check("b/free", ok=True)], degrade_threshold=2, now=NOW)

    assert _types(events) == {EventType.MODEL_REMOVED.value}
    assert updates["a/free"]["is_active"] is False


def test_removed_does_not_fire_again_while_still_gone():
    """사라진 채로 있는 동안 스캔마다 REMOVED가 반복되면 안 된다."""
    previous = {"a/free": _entry("a/free", is_active=False)}
    events, _ = _diff(previous, [], degrade_threshold=2, now=NOW)

    assert events == []


def test_a_model_that_returns_after_being_removed_is_added_again():
    previous = {"a/free": _entry("a/free", is_active=False)}
    events, updates = _diff(previous, [_check("a/free", ok=True)], degrade_threshold=2, now=NOW)

    assert _types(events) == {EventType.MODEL_ADDED.value}
    assert updates["a/free"]["is_active"] is True


@pytest.mark.parametrize("threshold", [1, 3, 5])
def test_degrade_threshold_is_configurable(threshold):
    previous = {"a/free": _entry("a/free", consecutive_failures=threshold - 1)}
    events, _ = _diff(previous, [_check("a/free", ok=False)], degrade_threshold=threshold, now=NOW)

    assert _types(events) == {EventType.MODEL_DEGRADED.value}
