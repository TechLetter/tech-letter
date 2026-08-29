"""헬스체크.

계약(04 §4.1)은 현행과 같다: `200 {"status":"ok"}` 또는
`503 {"status":"degraded", "checks": {...}}`. compose healthcheck가 이 경로를 본다.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health(response: Response) -> dict:
    checks: dict[str, str] = {}

    # Mongo 연결은 Phase 2에서 붙인다. 그때까지는 프로세스 생존만 보고한다.
    if all(v == "ok" for v in checks.values()):
        return {"status": "ok"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "degraded", "checks": checks}
