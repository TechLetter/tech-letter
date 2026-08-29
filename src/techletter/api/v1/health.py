"""헬스체크.

계약(04 §4.1)은 현행과 같다: `200 {"status":"ok"}` 또는
`503 {"status":"degraded", "checks": {...}}`. compose healthcheck가 이 경로를 본다.

의존성이 죽었을 때 **503을 내는 것이 목적**이다. 그래야 배포가 멈춘다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def health(request: Request, response: Response) -> dict:
    container = getattr(request.app.state, "container", None)
    if container is None:
        # 아직 부팅 중이다. 준비되지 않았다고 알린다.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "checks": {"mongo": "starting"}}

    checks = {"mongo": "ok" if await container.mongo.healthy() else "down"}
    if all(value == "ok" for value in checks.values()):
        return {"status": "ok"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "degraded", "checks": checks}
