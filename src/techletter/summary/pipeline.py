"""요약 파이프라인: 렌더 → 추출 → 검증 → 요약.

각 단계의 실패를 **재시도 가능/불가로 나눈다**.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.errors import PermanentError, RetryableError
from techletter.core.logging import get_logger
from techletter.summary.parser import extract_plain_text, extract_thumbnail
from techletter.summary.validator import validate_plain_text

if TYPE_CHECKING:  # pragma: no cover
    import httpx

    from techletter.summary.renderer import Renderer
    from techletter.summary.summarizer import Summarizer

__all__ = ["SummaryOutcome", "SummaryPipeline"]

logger = get_logger(__name__)

# 페이지가 아니라 차단·오류 화면을 받았다는 뜻의 검증 실패. 피드 본문으로 대신한다.
_BLOCKED_REASONS = frozenset({"bot_blocked", "unresolved_page", "error_page", "content_too_short"})


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

    async def _page_text(self, url: str) -> tuple[str, str]:
        html = await self._renderer.render(url)
        # 추출·검증 실패는 PermanentError다. 같은 페이지를 다시 열어도 같다.
        plain_text = extract_plain_text(html)
        validate_plain_text(plain_text)
        return html, plain_text

    async def run(self, url: str, feed_html: str | None = None) -> SummaryOutcome:
        """`feed_html`이 있으면 페이지가 막혔을 때 그것으로 요약한다.

        Medium은 서버 IP를 간헐적으로 막아 브라우저도 일반 HTTP도 403을 받는데,
        같은 글이 RSS에는 본문째 실려 있다.
        """
        try:
            html, plain_text = await self._page_text(url)
        except (RetryableError, PermanentError) as exc:
            blocked = isinstance(exc, RetryableError) or exc.reason in _BLOCKED_REASONS
            if not (feed_html and blocked):
                raise
            html = feed_html
            plain_text = extract_plain_text(html)
            validate_plain_text(plain_text)
            logger.info("page blocked; summarizing the feed content", extra={"url": url})

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
