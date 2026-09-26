"""공개 블로그 아이콘."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from techletter.api.deps import Ctx

router = APIRouter(prefix="/blogs", tags=["blogs"])

# 아이콘은 거의 안 바뀐다. 하루 캐시하고, 지나면 ETag로 확인만 한다.
_CACHE = "public, max-age=86400"


@router.get("/{blog_id}/icon")
async def blog_icon(ctx: Ctx, blog_id: str, request: Request) -> Response:
    from techletter.content.icons import BlogIconRepository  # noqa: PLC0415

    icon = await BlogIconRepository(ctx.db).get(blog_id)
    if icon is None:
        # 없는 것도 캐시한다 — 목록의 블로그마다 매번 404를 다시 묻지 않게.
        return Response(status_code=404, headers={"Cache-Control": "public, max-age=3600"})
    etag = f'"{icon["hash"]}"'
    headers = {"Cache-Control": _CACHE, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=icon["data"], media_type="image/webp", headers=headers)
