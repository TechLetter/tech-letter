"""RSS 파싱 — 네트워크 없이 픽스처 파일로만 검증한다."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from techletter.content.rss.feeder import RssFeeder, parse_feed
from techletter.core.errors import PermanentError, RetryableError
from techletter.core.http import HttpClients

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rss"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_rss2_and_skips_entries_without_link() -> None:
    items = parse_feed(fixture("rss2.xml"))

    assert [item.link for item in items] == [
        "https://example.com/blog/scaling-search",
        "https://example.com/blog/korean-title",
    ]
    assert items[1].title == "한글 제목도 잘 읽히는지"


def test_pubdate_offset_is_converted_to_utc() -> None:
    items = parse_feed(fixture("rss2.xml"))

    # +0900 09:00 == 00:00 UTC. struct_time 을 로컬 시각으로 해석하면 틀어진다.
    assert items[0].published_at == datetime(2025, 3, 3, 0, 0, tzinfo=UTC)


def test_atom_falls_back_to_updated_and_allows_missing_date() -> None:
    items = parse_feed(fixture("atom.xml"))

    assert items[0].published_at == datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    assert items[1].published_at is None


def test_control_characters_do_not_break_parsing() -> None:
    items = parse_feed(fixture("control-chars.xml"))

    assert [item.link for item in items] == ["https://dirty.example.com/a"]


def test_html_page_yields_no_items() -> None:
    assert parse_feed(fixture("not-a-feed.html"), source="https://x.test") == []


def test_limit_truncates() -> None:
    assert len(parse_feed(fixture("rss2.xml"), limit=1)) == 1
    assert len(parse_feed(fixture("rss2.xml"), limit=0)) == 2


def _feeder(handler: object) -> RssFeeder:
    clients = HttpClients()
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport, base_url="https://feed.test")
    clients._secure = client
    return RssFeeder(clients)


async def test_fetch_returns_items() -> None:
    feeder = _feeder(lambda request: httpx.Response(200, text=fixture("rss2.xml")))

    items = await feeder.fetch("https://feed.test/rss")

    assert len(items) == 2


@pytest.mark.parametrize("status", [404, 403, 410])
async def test_dead_feed_is_permanent(status: int) -> None:
    feeder = _feeder(lambda request: httpx.Response(status, text="<html>404</html>"))

    with pytest.raises(PermanentError) as excinfo:
        await feeder.fetch("https://feed.test/rss")
    # 응답 본문은 메시지에 넣지 않는다 — 어드민 화면에 404 HTML 이 뜨던 문제.
    assert "<html>" not in str(excinfo.value)
    assert excinfo.value.reason == f"http_{status}"


@pytest.mark.parametrize("status", [500, 502, 429])
async def test_server_errors_are_retryable(status: int) -> None:
    feeder = _feeder(lambda request: httpx.Response(status))

    with pytest.raises(RetryableError):
        await feeder.fetch("https://feed.test/rss")


async def test_connection_error_is_retryable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    with pytest.raises(RetryableError):
        await _feeder(boom).fetch("https://feed.test/rss")


async def test_tls_insecure_uses_a_separate_client() -> None:
    clients = HttpClients()

    secure = clients.get(verify=True)
    insecure = clients.get(verify=False)

    assert secure is not insecure
    assert clients.get(verify=True) is secure  # 재사용된다
    await clients.aclose()
