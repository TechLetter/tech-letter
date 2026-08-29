"""/api/v1 라우터 조립.

**선언 순서가 중요하다.** FastAPI는 선언 순서로 매칭하므로 고정 경로를
경로 변수보다 먼저 등록해야 한다. 현행 gin에서는 `/posts/bookmarks`가
`/posts/{id}`보다 뒤에 있어도 동작했지만 여기서는 아니다.
(v2에서는 북마크를 `/bookmarks`로 옮겨 이 충돌 자체를 없앴다 — 04 §2)
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

# Phase 3~6에서 도메인 라우터를 여기에 붙인다.
# api_router.include_router(auth.router)
# api_router.include_router(me.router)
# api_router.include_router(posts.router)
# ...
