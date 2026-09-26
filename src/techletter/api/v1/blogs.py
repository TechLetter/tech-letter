"""공개 블로그 아이콘."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from techletter.api.deps import Ctx

router = APIRouter(prefix="/blogs", tags=["blogs"])

# 어드민이 바꾼 아이콘이 한 시간 안에 보이게 한다. 지나면 ETag로 확인만 한다(304).
_CACHE = "public, max-age=3600"


@router.get("/{blog_id}/icon")
async def blog_icon(ctx: Ctx, blog_id: str, request: Request) -> Response:
    from techletter.content.icons import BlogIconRepository  # noqa: PLC0415

    icon = await BlogIconRepository(ctx.db).get(blog_id)
    if icon is None:
        # 404가 아니라 204다. `<img>`는 둘 다 onerror로 첫 글자 배지를 띄우지만, 404는
        # 브라우저 콘솔에 블로그마다 오류로 찍힌다. 없는 것도 캐시해 매번 다시 묻지 않는다.
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=3600"})
    etag = f'"{icon["hash"]}"'
    headers = {"Cache-Control": _CACHE, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=icon["data"], media_type="image/webp", headers=headers)
