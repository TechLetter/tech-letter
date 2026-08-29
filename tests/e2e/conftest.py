"""E2E 픽스처 — 실제 브라우저로 프론트+백엔드를 함께 확인한다.

계약을 전면 재설계했으니 "스냅샷 완전 일치"로는 판정할 수 없다.
**화면이 실제로 동작하는가**가 최종 판정이다(07 §2).

브라우저도 **async API** 를 쓴다. 이 저장소의 pytest 는 `asyncio_mode=auto`
라서 모든 테스트가 이벤트 루프 안에서 돈다 — 동기 Playwright 는 그 안에서
동작하지 않는다.

전제:
1. API 가 `E2E_API_URL`(기본 http://localhost:8080)에서 돌고 있다.
2. 그 API 가 보는 Mongo 를 `E2E_MONGO_URI` 로 직접 만질 수 있다.
3. 프론트 정적 빌드가 `E2E_UI_DIST` 에 있다(기본 `../tech-letter_ui/dist`).

셋 중 하나라도 없으면 skip 한다. 준비 절차는 `docs/plan/08-deployment-and-ops.md`.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
API_URL = os.environ.get("E2E_API_URL", "http://localhost:8080")
MONGO_URI = os.environ.get("E2E_MONGO_URI", "mongodb://localhost:27018")
MONGO_DB = os.environ.get("E2E_MONGO_DB", "techletter_compose")
UI_DIST = Path(os.environ.get("E2E_UI_DIST", REPO.parent / "tech-letter_ui" / "dist"))
JWT_SECRET = os.environ.get("JWT_SECRET", "compose-test-secret-at-least-32-bytes-long")

ADMIN_CODE = "google:e2e-admin"
USER_CODE = "google:e2e-user"


# 포트를 고정한다. API 의 CORS 허용 목록에 이 오리진이 들어가야 한다.
UI_PORT = int(os.environ.get("E2E_UI_PORT", "4173"))


class _ReusableServer(http.server.ThreadingHTTPServer):
    # 직전 실행이 남긴 소켓 때문에 바인드가 막히지 않게 한다.
    allow_reuse_address = True
    daemon_threads = True


class _SpaHandler(http.server.SimpleHTTPRequestHandler):
    """SPA 라우팅: 파일이 없으면 index.html 을 준다."""

    def do_GET(self) -> None:
        target = Path(self.translate_path(self.path))
        if not target.exists() and "." not in Path(self.path).name:
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        """정적 서버 로그를 끈다. 테스트 출력이 요청 로그로 덮인다."""
        return


@pytest.fixture(scope="session")
def ui_server() -> Iterator[str]:
    if not (UI_DIST / "index.html").exists():
        pytest.skip(f"프론트 빌드가 없다 ({UI_DIST}). `npm run build` 를 먼저 돌린다.")

    handler = functools.partial(_SpaHandler, directory=str(UI_DIST))
    try:
        server = _ReusableServer(("127.0.0.1", UI_PORT), handler)
    except OSError as exc:
        pytest.skip(f"E2E UI 포트 {UI_PORT} 를 열 수 없다: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{UI_PORT}"
    finally:
        server.shutdown()


@pytest.fixture(scope="session")
def api_url() -> str:
    import httpx

    try:
        response = httpx.get(f"{API_URL}/health", timeout=3.0)
        response.raise_for_status()
    except Exception as exc:
        pytest.skip(f"E2E 대상 API 가 없다 ({API_URL}): {exc}")
    return API_URL


@pytest.fixture
async def db(api_url):
    from pymongo import AsyncMongoClient

    client = AsyncMongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=3000)
    database = client[MONGO_DB]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        await client.close()
        pytest.skip(f"E2E Mongo 에 접속할 수 없다 ({MONGO_URI}): {exc}")

    for name in await database.list_collection_names():
        await database[name].drop()
    yield database
    await client.close()


def token_for(user_code: str, role: str = "user") -> str:
    from pydantic import SecretStr

    from techletter.core.security.tokens import issue_token
    from techletter.settings import AuthSettings

    settings = AuthSettings(
        JWT_SECRET=SecretStr(JWT_SECRET),
        GOOGLE_OAUTH_CLIENT_ID="x",
        GOOGLE_OAUTH_CLIENT_SECRET=SecretStr("x"),
        GOOGLE_OAUTH_REDIRECT_URL="http://localhost/cb",
        AUTH_LOGIN_SUCCESS_REDIRECT_URL="http://localhost/ok",
    )
    return issue_token(settings, user_code, role)


@pytest.fixture
async def browser():
    """브라우저 하나를 테스트마다 띄운다.

    async API 를 쓴다 — 이 저장소는 `asyncio_mode=auto` 라 모든 테스트가
    이벤트 루프 안에서 돌고, 동기 Playwright 는 거기서 동작하지 않는다.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        instance = await driver.chromium.launch()
        try:
            yield instance
        finally:
            await instance.close()


@pytest.fixture
async def page(browser):
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    target = await context.new_page()
    try:
        yield target
    finally:
        await context.close()


@pytest.fixture
async def sign_in(page, ui_server):
    """토큰을 localStorage 에 넣어 로그인 상태로 만든다.

    OAuth 왕복을 E2E 마다 돌 수는 없다. 토큰 발급은 계약 테스트가 검증한다.
    """

    async def _sign_in(user_code: str = USER_CODE, role: str = "user") -> None:
        await page.goto(f"{ui_server}/")
        await page.evaluate(
            "([key, value]) => localStorage.setItem(key, value)",
            ["TECHLETTER_ACCESS_TOKEN", token_for(user_code, role)],
        )

    return _sign_in


@pytest.fixture
async def console_errors(page):
    """콘솔 에러를 모은다. 각 시나리오는 0을 단정한다."""
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors


@pytest.fixture(autouse=True)
async def _capture_on_failure(request, page):
    """실패하면 스크린샷을 남긴다(07 §2.2)."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is not None and report.failed:
        artifacts = REPO / "tests" / "e2e" / "_artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(Exception):
            await page.screenshot(path=str(artifacts / f"{request.node.name}.png"), full_page=True)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())


# ── 시드 ────────────────────────────────────────────────────────────
async def seed_content(db, *, posts: int = 15) -> dict:
    """블로그 1개 + 요약된 포스트 여러 개.

    문서 모양은 도메인 모델의 `to_mongo()` 로 만든다. 손으로 dict 를 쓰면
    스키마가 갈라진다.
    """
    from datetime import UTC, datetime

    from techletter.content.models import AISummary, Blog, Post, StatusFlags

    blog = Blog(
        name="Alpha Engineering", url="https://alpha.test", rss_url="https://alpha.test/rss"
    )
    blog.id = (await db["blogs"].insert_one(blog.to_mongo())).inserted_id

    documents = []
    for index in range(posts):
        post = Post(
            blog_id=blog.id,
            blog_name=blog.name,
            title=f"테스트 포스트 {index:02d}",
            link=f"https://alpha.test/{index}",
            published_at=datetime(2025, 3, 1 + index % 28, tzinfo=UTC),
            plain_text=f"본문 {index}",
            status=StatusFlags(ai_summarized=True, embedded=True),
            aisummary=AISummary(
                categories=["Backend" if index % 2 else "AI"],
                tags=["Kafka"] if index % 2 else ["LLM"],
                summary=f"요약 {index}",
                model_name="gemini-3-flash-preview",
                generated_at=datetime(2025, 3, 1, tzinfo=UTC),
            ),
        )
        documents.append(post.to_mongo())
    result = await db["posts"].insert_many(documents)
    return {"blog": blog, "post_ids": [str(oid) for oid in result.inserted_ids]}


async def seed_users(db) -> None:
    from techletter.core.time import utcnow
    from techletter.users.models import User

    for code, role, name in (
        (USER_CODE, "user", "E2E 사용자"),
        (ADMIN_CODE, "admin", "E2E 관리자"),
    ):
        user = User(
            user_code=code,
            provider="google",
            provider_sub=code,
            email=f"{code}@e2e.test",
            name=name,
            role=role,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        await db["users"].update_one({"user_code": code}, {"$set": user.to_mongo()}, upsert=True)


async def grant_credits(db, user_code: str, amount: int) -> None:
    from datetime import timedelta

    from techletter.core.time import utcnow
    from techletter.users.models import Credit

    credit = Credit(
        user_code=user_code,
        amount=amount,
        original_amount=amount,
        source="admin",
        reason="e2e",
        expired_at=utcnow() + timedelta(days=1),
    )
    await db["credits"].insert_one(credit.to_mongo())
