"""v1 골든 스냅샷과 v2 응답을 항목별로 대조한다 (스텝 6.10).

`tests/contract/snapshots/current/`(2026-08-29 운영에서 뜬 것)의 각 케이스를
새 API에 다시 던지고, 타입 토큰으로 정규화한 모양을 비교해 표로 낸다.

목적은 "차이가 없는지" 확인하는 것이 **아니다**. v2는 의도적으로 계약을
바꿨다. 확인할 것은 남은 차이가 전부 04 문서에 적힌 의도된 변경인가다.

    uv run python scripts/contract_diff.py            # 표 출력
    uv run python scripts/contract_diff.py --write    # v2 스냅샷 저장
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

SNAPSHOTS = ROOT / "tests" / "contract" / "snapshots"
CURRENT = SNAPSHOTS / "current"
V2 = SNAPSHOTS / "v2"

# 골든 스냅샷은 `_request.path`만 저장해 쿼리스트링을 잃었다. 케이스 이름이
# 무엇을 시험했는지 말해 주므로 여기서 복원한다. 이게 없으면 `bad_*` 케이스가
# 전부 "조건 없는 조회"로 바뀌어 비교가 무의미해진다.
QUERIES = {
    "posts__bad_date": "published_from=not-a-date",
    "posts__bad_page": "page=abc&page_size=xyz",
    "posts__date_only": "published_to=2025-03-01",
    "posts__empty_category": "categories=",
    "posts__repeated_tags": "tags=Kafka&tags=Go",
    "admin_posts__filtered": "summarized=true",
    "filters_categories__scoped": "tags=Kafka",
    "trends_rising__bad_limit": "limit=abc",
    "trends_rising__bad_period": "period=7d",
    "trends_series": "tags=Kafka",
    "trends_series__bad_interval": "tags=Kafka&interval=hour",
}
# Authorization 헤더를 직접 지정하는 케이스.
RAW_AUTH = {
    "users_profile__bad_token": "Bearer not-a-real-token",
    "users_profile__basic": "Basic dXNlcjpwYXNz",
    "users_profile__empty_token": "Bearer ",
    "admin_posts__forbidden": "",
}
# 재현할 수 없는 케이스와 그 이유.
UNREPLAYABLE = {
    "health": "v1 스냅샷은 프론트 도메인의 /health(text/html)를 찍었다 — API 응답이 아니다",
    "posts_detail": "운영 ObjectId를 그대로 담고 있어 시드 데이터로 재현 불가",
    "chatbot_sessions__missing": "경로에 {id} 자리표시자가 남아 있다",
    "posts_detail__missing": "경로에 {id} 자리표시자가 남아 있다",
}

# v1 경로 → v2 경로. None이면 v2에서 사라진 경로다.
PATH_MAP = {
    "/api/v1/users/profile": "/api/v1/me",
    "/api/v1/posts/bookmarks": "/api/v1/bookmarks",
    "/api/v1/chatbot/sessions": "/api/v1/chat/sessions",
    "/api/v1/chatbot/suggested-questions": "/api/v1/chat/suggested-questions",
    "/api/v1/admin/chatbot/suggested-questions": "/api/v1/admin/suggested-questions",
}


def token(value: Any) -> Any:
    """값을 타입 토큰으로 바꾼다. 실제 데이터가 아니라 모양을 비교하기 위해."""
    if isinstance(value, dict):
        return {k: token(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [token(value[0])] if value else []
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int):
        return "<int>"
    if isinstance(value, float):
        return "<float>"
    if value is None:
        return "<null>"
    text = str(value)
    if len(text) == 24 and all(c in "0123456789abcdef" for c in text.lower()):
        return "<oid>"
    if text.startswith(("http://", "https://")):
        return "<url>"
    if len(text) >= 19 and text[4] == "-" and text[7] == "-":
        return "<datetime>"
    return "<str>"


def keys_of(body: Any) -> set[str]:
    return set(body) if isinstance(body, dict) else set()


def map_path(path: str) -> str:
    for old, new in PATH_MAP.items():
        if path.startswith(old):
            return new + path[len(old) :]
    return path


async def capture(cases: dict[str, dict]) -> dict[str, dict]:
    """새 앱에 같은 요청을 던진다. 데이터는 계약 테스트와 같은 시드를 쓴다."""
    import os

    os.environ.setdefault(
        "MONGO_URI", os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27018")
    )
    os.environ["MONGO_DB_NAME"] = "techletter_diff"
    os.environ.setdefault("JWT_SECRET", "x" * 40)
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "c")
    os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "s")
    os.environ.setdefault("GOOGLE_OAUTH_REDIRECT_URL", "http://localhost/cb")
    os.environ.setdefault("AUTH_LOGIN_SUCCESS_REDIRECT_URL", "http://localhost/ok")

    from httpx import ASGITransport, AsyncClient

    from techletter.app import create_app
    from techletter.core.security.tokens import issue_token
    from techletter.settings import Settings

    settings = Settings.load()
    app = create_app(settings)
    results: dict[str, dict] = {}

    async with app.router.lifespan_context(app):
        await _seed(app.state.container)
        user = {"Authorization": f"Bearer {issue_token(settings.auth, 'google:alice')}"}
        admin = {"Authorization": f"Bearer {issue_token(settings.auth, 'google:root', 'admin')}"}
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            for name, case in cases.items():
                if name in UNREPLAYABLE:
                    results[name] = {
                        "_request": {"path": map_path(case["_request"]["path"]), "authed": False},
                        "status": None,
                        "content_type": None,
                        "body": None,
                        "skipped": UNREPLAYABLE[name],
                    }
                    continue
                request = case.get("_request", {})
                path = map_path(request.get("path", ""))
                if name in QUERIES:
                    path = f"{path}?{QUERIES[name]}"
                headers: dict[str, str] = {}
                if request.get("authed"):
                    headers = admin if "/admin/" in path else user
                if name in RAW_AUTH:
                    headers = {"Authorization": RAW_AUTH[name]} if RAW_AUTH[name] else {}
                response = await client.get(path, headers=headers)
                body: Any = None
                if response.headers.get("content-type", "").startswith("application/json"):
                    body = token(response.json())
                results[name] = {
                    "_request": {"path": path, "authed": bool(request.get("authed"))},
                    "status": response.status_code,
                    "content_type": response.headers.get("content-type", "").split(";")[0],
                    "body": body,
                }
        await app.state.container.db.client.drop_database("techletter_diff")
    return results


async def _seed(container) -> None:
    from datetime import UTC, datetime

    from techletter.content.models import AISummary, Blog, Post, StatusFlags

    for name in await container.db.list_collection_names():
        await container.db[name].drop()

    blog = await container.blogs.insert(
        Blog(name="Alpha", url="https://alpha.test", rss_url="https://alpha.test/rss")
    )
    for index in range(2):
        await container.posts.insert(
            Post(
                blog_id=blog.id,
                blog_name=blog.name,
                title=f"제목 {index}",
                link=f"https://alpha.test/{index}",
                published_at=datetime(2025, 3, index + 1, tzinfo=UTC),
                thumbnail_url=f"https://alpha.test/{index}.png",
                plain_text="본문",
                status=StatusFlags(ai_summarized=True, embedded=True),
                aisummary=AISummary(
                    categories=["Backend"],
                    tags=["Kafka"],
                    summary="요약",
                    model_name="m",
                    generated_at=datetime(2025, 3, 1, tzinfo=UTC),
                ),
            )
        )
    # 토큰의 sub와 같은 user_code로 넣는다. upsert_from_oauth는 uuid를 새로
    # 만들어 토큰과 어긋난다.
    from techletter.users.models import User
    from techletter.users.repositories import UserRepository

    await UserRepository(container.db).upsert(
        User(
            user_code="google:alice",
            provider="google",
            provider_sub="s",
            email="a@b.c",
            name="A",
            profile_image="https://img.test/a.png",
        )
    )
    await container.suggested_questions.create("추천 질문")


def verdict(old: dict, new: dict) -> str:
    if new.get("skipped"):
        return f"재현 불가 — {new['skipped']}"
    if old["status"] != new["status"]:
        return f"상태 {old['status']}→{new['status']}"
    old_keys, new_keys = keys_of(old.get("body")), keys_of(new.get("body"))
    if old_keys == new_keys:
        return "동일"
    gone = sorted(old_keys - new_keys)
    added = sorted(new_keys - old_keys)
    parts = []
    if gone:
        parts.append("삭제 " + ", ".join(gone))
    if added:
        parts.append("추가 " + ", ".join(added))
    return " · ".join(parts)


def main() -> int:
    cases = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CURRENT.glob("*.json"))
        if path.stem != "_index"
    }
    results = asyncio.run(capture(cases))

    print("| 케이스 | 경로(v2) | v1 | v2 | 차이 |")
    print("|---|---|---|---|---|")
    for name, old in cases.items():
        new = results[name]
        status = "—" if new.get("skipped") else new["status"]
        print(
            f"| `{name}` | `{new['_request']['path']}` | {old['status']} "
            f"| {status} | {verdict(old, new)} |"
        )

    if "--write" in sys.argv:
        V2.mkdir(parents=True, exist_ok=True)
        for name, payload in results.items():
            (V2 / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(f"\nv2 스냅샷 {len(results)}건을 {V2}에 저장했다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
