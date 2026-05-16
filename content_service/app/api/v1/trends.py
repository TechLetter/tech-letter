from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from common.schemas.pagination import PaginatedResponse

from ...services.trends_service import TrendsService, get_trends_service
from ..schemas.posts import PostResponse
from ..schemas.trends import RisingTagsResponse, TrendSeriesResponse


router = APIRouter()


@router.get(
    "/rising",
    response_model=RisingTagsResponse,
    summary="급상승 태그 조회",
    description="현재 기간과 직전 동일 기간을 비교해 증가량이 큰 태그를 반환한다.",
)
def get_rising_tags(
    period: str = Query(
        "90d",
        pattern="^(30d|90d|180d|365d)$",
        description="조회 기간",
    ),
    limit: int = Query(5, ge=1, le=20, description="반환할 태그 개수"),
    service: TrendsService = Depends(get_trends_service),
) -> RisingTagsResponse:
    try:
        return service.get_rising_tags(period=period, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/series",
    response_model=TrendSeriesResponse,
    summary="태그 시계열 조회",
    description="선택한 태그의 기간별 포스트 수와 출처 수를 반환한다.",
)
def get_tag_series(
    tags: List[str] = Query(
        default_factory=list,
        description="조회할 태그 목록",
    ),
    period: str = Query(
        "90d",
        pattern="^(30d|90d|180d|365d)$",
        description="조회 기간",
    ),
    interval: str = Query(
        "week",
        pattern="^(day|week|month)$",
        description="시계열 집계 단위",
    ),
    service: TrendsService = Depends(get_trends_service),
) -> TrendSeriesResponse:
    try:
        return service.get_tag_series(tags=tags, period=period, interval=interval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/posts",
    response_model=PaginatedResponse[PostResponse],
    summary="트렌드 관련 포스트 조회",
    description="선택한 태그와 기간에 해당하는 포스트 목록을 반환한다.",
)
def list_trend_posts(
    tags: List[str] = Query(
        default_factory=list,
        description="조회할 태그 목록",
    ),
    period: str = Query(
        "90d",
        pattern="^(30d|90d|180d|365d)$",
        description="조회 기간",
    ),
    page: int = Query(1, ge=1, description="조회할 페이지"),
    page_size: int = Query(10, ge=1, le=50, description="페이지당 아이템 개수"),
    service: TrendsService = Depends(get_trends_service),
) -> PaginatedResponse[PostResponse]:
    try:
        posts, total = service.list_trend_posts(
            tags=tags,
            period=period,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PaginatedResponse(
        items=[PostResponse.from_domain(post) for post in posts],
        total=total,
        page=page,
        page_size=page_size,
    )
