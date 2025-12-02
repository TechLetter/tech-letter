from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/health", summary="헬스 체크")
async def health() -> dict[str, str]:
    return {"status": "ok"}
