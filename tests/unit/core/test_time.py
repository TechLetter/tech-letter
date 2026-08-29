"""시간 유틸 — 프론트가 `new Date()`로 파싱하므로 오프셋이 반드시 있어야 한다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from techletter.core.time import ensure_utc, parse_rfc3339_or_date, to_iso_z, utcnow


def test_utcnow_is_aware_utc():
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ensure_utc_treats_naive_as_utc():
    naive = datetime(2026, 8, 29, 12, 0, 0)  # noqa: DTZ001
    assert ensure_utc(naive).tzinfo is UTC


def test_ensure_utc_converts_other_offsets():
    kst = datetime(2026, 8, 29, 21, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    assert ensure_utc(kst).hour == 12


def test_to_iso_z_has_millis_and_z_suffix():
    value = datetime(2026, 8, 29, 11, 22, 33, 456789, tzinfo=UTC)
    assert to_iso_z(value) == "2026-08-29T11:22:33.456Z"


def test_to_iso_z_none():
    assert to_iso_z(None) is None


def test_parse_rfc3339():
    parsed = parse_rfc3339_or_date("2026-08-29T11:22:33Z")
    assert parsed == datetime(2026, 8, 29, 11, 22, 33, tzinfo=UTC)


def test_parse_date_only_start_of_day():
    parsed = parse_rfc3339_or_date("2026-08-29")
    assert parsed == datetime(2026, 8, 29, 0, 0, 0, tzinfo=UTC)


def test_parse_date_only_end_of_day():
    """`published_to`에 날짜만 오면 그 날의 끝까지 포함한다(현행 게이트웨이 동작)."""
    parsed = parse_rfc3339_or_date("2026-08-29", end_of_day=True)
    assert parsed is not None
    assert parsed.hour == 23
    assert parsed.minute == 59
    assert parsed.date() == datetime(2026, 8, 29, tzinfo=UTC).date()


def test_parse_garbage_returns_none():
    assert parse_rfc3339_or_date("nope") is None
    assert parse_rfc3339_or_date("") is None
