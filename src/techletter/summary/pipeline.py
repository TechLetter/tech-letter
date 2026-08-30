"""요약 파이프라인: 렌더 → 추출 → 검증 → 요약.

각 단계의 실패를 **재시도 가능/불가로 나눈다**.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.logging import get_logger
from techletter.summary.parser import extract_plain_text, extract_thumbnail
from techletter.summary.validator import validate_plain_text

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from techletter.summary.renderer import Renderer
    from techletter.summary.summarizer import Summarizer

__all__ = ["SummaryOutcome", "SummaryPipeline"]

logger = get_logger(__name__)


@dataclass(slots=True)
class SummaryOutcome:
    summary: str
    categories: list[str]
    tags: list[str]
    model_name: str
    plain_text: str
    thumbnail_url: str


class SummaryPipeline:
    def __init__(
        self,
        renderer: Renderer,
        summarizer: Summarizer,
        image_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._renderer = renderer
        self._summarizer = summarizer
        self._image_client = image_client

    async def run(self, url: str) -> SummaryOutcome:
        html = await self._renderer.render(url)

        # 추출·검증 실패는 PermanentError다. 같은 페이지를 다시 열어도 같다.
        plain_text = extract_plain_text(html)
        validate_plain_text(plain_text)

        result = await self._summarizer.summarize(plain_text)
        if result.truncated_input:
            logger.info("summary input truncated", extra={"url": url})

        # 썸네일은 있으면 좋은 것이다. 실패해도 요약을 버리지 않는다.
        thumbnail = ""
        try:
            thumbnail = await extract_thumbnail(html, url, self._image_client)
        except Exception:
            logger.warning("thumbnail extraction failed", extra={"url": url})

        return SummaryOutcome(
            summary=result.summary,
            categories=result.categories,
            tags=result.tags,
            model_name=result.model_name,
            plain_text=plain_text,
            thumbnail_url=thumbnail,
        )
