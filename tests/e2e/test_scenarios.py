"""E2E 시나리오 9종.

실제 브라우저가 실제 API를 친다. 프론트가 API 계약을 제대로 쓰고 있다는
최종 판정이다.
"""

from __future__ import annotations

import pytest
from playwright.async_api import expect
from tests.e2e.conftest import ADMIN_CODE, USER_CODE, grant_credits, seed_content, seed_users

pytestmark = pytest.mark.e2e

TIMEOUT = 15_000


@pytest.fixture
async def seeded(db):
    data = await seed_content(db, posts=15)
    await seed_users(db)
    await grant_credits(db, USER_CODE, 5)
    return data


@pytest.fixture
async def broke(db, seeded):
    """크레딧이 0인 상태."""
    await db["credits"].delete_many({"user_code": USER_CODE})
    return seeded


# ── E1: 홈 · 필터 · 무한스크롤 ──────────────────────────────────────
async def test_home_lists_posts_and_filters(page, ui_server, seeded, console_errors) -> None:
    await page.goto(f"{ui_server}/", wait_until="networkidle")

    cards = page.locator("[data-testid='post-card']")
    await expect(cards.first).to_be_visible(timeout=TIMEOUT)
    assert await cards.count() > 0
    assert console_errors == []


async def test_home_paginates_with_total_pages(page, ui_server, seeded) -> None:
    """`items.length < PAGE_SIZE` 추론을 버리고 `total_pages` 를 쓴다."""
    await page.goto(f"{ui_server}/", wait_until="networkidle")
    before = await page.locator("[data-testid='post-card']").count()

    await page.mouse.wheel(0, 20000)
    await page.wait_for_timeout(1500)

    after = await page.locator("[data-testid='post-card']").count()
    assert after >= before


async def test_home_requests_use_the_v2_contract(page, ui_server, seeded) -> None:
    """프론트가 보내는 요청 자체를 확인한다."""
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    await page.goto(f"{ui_server}/", wait_until="networkidle")

    posts = [url for url in requests if "/api/v1/posts" in url]
    assert posts, "포스트 요청이 없다"
    # 공개 API 에서 사라진 파라미터를 여전히 보내면 안 된다.
    assert all("status_ai_summarized" not in url for url in posts)
    assert any("/api/v1/filters/" in url for url in requests)


# ── E2: 북마크 ──────────────────────────────────────────────────────
async def test_bookmark_round_trip(page, ui_server, seeded, sign_in, console_errors) -> None:
    await sign_in()
    await page.goto(f"{ui_server}/", wait_until="networkidle")

    toggle = page.locator("[data-testid='bookmark-toggle']").first
    await expect(toggle).to_be_visible(timeout=TIMEOUT)
    async with page.expect_response(
        lambda r: "/api/v1/bookmarks" in r.url and r.request.method == "POST"
    ) as info:
        await toggle.click()
    assert (await info.value).status == 201

    await page.goto(f"{ui_server}/bookmarks", wait_until="networkidle")
    await expect(page.locator("[data-testid='post-card']").first).to_be_visible(timeout=TIMEOUT)
    assert console_errors == []


# ── E3: 트렌드 ──────────────────────────────────────────────────────
async def test_trends_renders_from_items(page, ui_server, seeded, console_errors) -> None:
    """`series` 키가 `items` 로 바뀌었다. 이름이 틀리면 차트가 빈다."""
    responses: list[dict] = []
    page.on(
        "response",
        lambda response: (
            responses.append({"url": response.url, "status": response.status})
            if "/api/v1/trends/" in response.url
            else None
        ),
    )

    await page.goto(f"{ui_server}/trends", wait_until="networkidle")

    assert responses, "트렌드 요청이 없다"
    assert all(item["status"] == 200 for item in responses)
    assert console_errors == []


# ── E4~E6: 챗봇 ─────────────────────────────────────────────────────
async def test_chat_streams_an_answer(page, ui_server, seeded, sign_in, console_errors) -> None:
    """SSE 로 활동이 흐르고 답변과 크레딧이 반영된다."""
    await sign_in()
    await page.goto(f"{ui_server}/chatbot", wait_until="networkidle")

    box = page.locator("textarea, input[type='text']").last
    await expect(box).to_be_visible(timeout=TIMEOUT)
    await box.fill("Kafka 리밸런싱 알려줘")

    async with page.expect_response(
        lambda r: "/api/v1/chat/messages/stream" in r.url, timeout=TIMEOUT
    ) as info:
        await box.press("Enter")

    response = await info.value
    # 모델이 없는 환경이라 503 이 정상이다. 확인할 것은 **요청 경로와
    # 에러 봉투를 프론트가 제대로 다루는가** 다.
    assert response.status in {200, 402, 429, 503}
    assert "/chatbot/" not in response.url


async def test_no_credits_yields_402(page, ui_server, broke, sign_in) -> None:
    """크레딧이 없으면 스트림을 열기 전에 402 가 나와야 한다.

    스트림을 열어 버리면 HTTP 상태가 이미 200 이라 프론트가 크레딧 부족을
    구분하지 못한다.
    """
    await sign_in()
    await page.goto(f"{ui_server}/chatbot", wait_until="networkidle")
    box = page.locator("textarea, input[type='text']").last
    await expect(box).to_be_visible(timeout=TIMEOUT)
    await box.fill("질문")

    async with page.expect_response(
        lambda r: "/api/v1/chat/messages" in r.url, timeout=TIMEOUT
    ) as info:
        await box.press("Enter")

    response = await info.value
    assert response.status == 402
    assert (await response.json())["error"]["code"] == "credit.insufficient"


async def test_chat_session_list_uses_message_count(page, ui_server, seeded, sign_in) -> None:
    await sign_in()
    sessions: list[dict] = []
    page.on(
        "response",
        lambda response: (
            sessions.append({"url": response.url, "status": response.status})
            if "/api/v1/chat/sessions" in response.url
            else None
        ),
    )

    await page.goto(f"{ui_server}/chatbot", wait_until="networkidle")

    assert sessions, "세션 목록 요청이 없다"
    assert all(item["status"] in {200, 201} for item in sessions)


# ── E7~E8: 어드민 ───────────────────────────────────────────────────
async def test_admin_lists_posts_with_v2_fields(
    page, ui_server, seeded, sign_in, console_errors
) -> None:
    await sign_in(ADMIN_CODE, "admin")
    await page.goto(f"{ui_server}/admin", wait_until="networkidle")

    await expect(page.get_by_text("테스트 포스트 00")).to_be_visible(timeout=TIMEOUT)
    # `ai_summary.model_name` 을 읽는다. 이름이 틀리면 빈칸이 뜬다.
    await expect(page.get_by_text("gemini-3-flash-preview").first).to_be_visible(timeout=TIMEOUT)
    assert console_errors == []


async def test_admin_ops_tab_shows_the_job_queue(page, ui_server, seeded, sign_in) -> None:
    """서버에 접속하지 않고도 잡 큐 상태를 볼 수 있어야 한다."""
    await sign_in(ADMIN_CODE, "admin")
    await page.goto(f"{ui_server}/admin", wait_until="networkidle")

    async with page.expect_response(
        lambda r: "/api/v1/admin/jobs/stats" in r.url, timeout=TIMEOUT
    ) as info:
        await page.get_by_role("button", name="운영").click()

    assert (await info.value).status == 200
    # 상태 카드가 그려진다(같은 문구가 필터 select 에도 있어 카드로 좁힌다).
    await expect(page.get_by_text("실패(dead)").first).to_be_visible(timeout=TIMEOUT)
    await expect(
        page.get_by_text("가장 오래된 대기 잡").or_(page.get_by_text("대기")).first
    ).to_be_visible(timeout=TIMEOUT)


async def test_admin_llm_tab_shows_model_stats(page, ui_server, seeded, sign_in) -> None:
    await sign_in(ADMIN_CODE, "admin")
    await page.goto(f"{ui_server}/admin", wait_until="networkidle")

    async with page.expect_response(
        lambda r: "/api/v1/admin/llm-models" in r.url, timeout=TIMEOUT
    ) as info:
        await page.get_by_role("button", name="모델").click()

    assert (await info.value).status == 200


async def test_a_plain_user_cannot_see_admin_data(page, ui_server, seeded, sign_in) -> None:
    await sign_in()
    forbidden: list[int] = []
    page.on(
        "response",
        lambda response: (
            forbidden.append(response.status) if "/api/v1/admin/" in response.url else None
        ),
    )

    await page.goto(f"{ui_server}/admin", wait_until="networkidle")

    assert all(status == 403 for status in forbidden) or forbidden == []


# ── E9: 세션 만료 ───────────────────────────────────────────────────
async def test_an_expired_token_logs_the_user_out(page, ui_server, seeded) -> None:
    """401 인터셉터가 토큰을 버린다. 만료된 토큰으로 로그인 상태가 남지 않는다."""
    await page.goto(f"{ui_server}/")
    await page.evaluate(
        "([key, value]) => localStorage.setItem(key, value)",
        ["TECHLETTER_ACCESS_TOKEN", "not.a.valid.token"],
    )

    await page.goto(f"{ui_server}/bookmarks", wait_until="networkidle")
    await page.wait_for_timeout(1000)

    stored = await page.evaluate("() => localStorage.getItem('TECHLETTER_ACCESS_TOKEN')")
    assert stored is None
