"""요약 파이프라인. 두 단계로 나뉘어 있고 각자 다른 잡이 부른다.

- `fetch`: 원문 확보 → 추출 → 검증 → 썸네일 (`content.fetch_requested`)
- `summarize`: 저장된 본문 → LLM 요약 (`summary.requested`)

나눈 이유: 원문이 막혀 재시도할 때 LLM을 부르지 않고, LLM 한도에 걸려도
받아 둔 원문을 버리지 않으며, 원문을 다시 받지 않고 재요약할 수 있다.
각 단계의 실패는 **재시도 가능/불가로 나눈다**.
"""

from __future__ import annotations

import re
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

__all__ = ["FetchedContent", "SummaryOutcome", "SummaryPipeline"]

logger = get_logger(__name__)

# 추출한 피드 본문이 이보다 짧으면 발췌다.
FEED_TEXT_MIN_CHARS = 1000
# 발췌 피드의 끝맺음. 본문 끝에 이게 있으면 잘린 글이다.
_TRUNCATED_TAIL = re.compile(
    r"(continue reading|read more|read the full|계속 읽기|더 보기|원문 보기)[^\n]{0,40}$"
    r"|(…|\.\.\.)\s*$",
    re.I,
)


def usable_feed_text(feed_html: str | None) -> str | None:
    """피드 본문을 원문 대신 써도 되면 추출한 텍스트, 아니면 None.

    HTML 길이만 보면 안 된다 — CMU 피드는 9천 자인데 내용 없는 태그 틀뿐이라
    추출하면 3자다. 앞부분만 싣고 "Continue reading"으로 끝나는 피드도 있다.
    """
    if not feed_html:
        return None
    text = extract_plain_text(feed_html).strip()
    if len(text) < FEED_TEXT_MIN_CHARS or _TRUNCATED_TAIL.search(text[-200:]):
        return None
    try:
        validate_plain_text(text)
    except PermanentError:
        return None
    return text


# 페이지가 아니라 차단·오류 화면을 받았다는 뜻의 검증 실패. 피드 본문으로 대신한다.
_BLOCKED_REASONS = frozenset({"bot_blocked", "unresolved_page", "error_page", "content_too_short"})


@dataclass(slots=True)
class FetchedContent:
    plain_text: str
    thumbnail_url: str


@dataclass(slots=True)
class SummaryOutcome:
    summary: str
    categories: list[str]
    tags: list[str]
    model_name: str


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

    async def _page_text(self, url: str, attempts: int | None) -> tuple[str, str]:
        html = await self._renderer.render(url, attempts=attempts)
        # 추출·검증 실패는 PermanentError다. 같은 페이지를 다시 열어도 같다.
        plain_text = extract_plain_text(html)
        validate_plain_text(plain_text)
        return html, plain_text

    async def fetch(self, url: str, feed_html: str | None = None) -> FetchedContent:
        """원문 본문과 썸네일. `feed_html`이 있으면 페이지가 막혔을 때 그것을 쓴다.

        Medium은 서버 IP를 막아 브라우저도 일반 HTTP도 403을 받는데, 같은 글이
        RSS에는 본문째 실려 있다.
        """
        feed_text = usable_feed_text(feed_html)
        try:
            # 쓸 만한 대체 본문이 있으면 막힌 브라우저를 여러 번 열며 기다리지 않는다
            # (Medium은 서버 IP에서 매번 막힌다 — 재시도마다 수십 초가 샌다).
            html, plain_text = await self._page_text(url, attempts=1 if feed_text else None)
        except (RetryableError, PermanentError) as exc:
            blocked = isinstance(exc, RetryableError) or exc.reason in _BLOCKED_REASONS
            if not (feed_html and feed_text and blocked):
                raise
            html, plain_text = feed_html, feed_text
            logger.info("page blocked; using the feed content", extra={"url": url})

        # 썸네일은 있으면 좋은 것이다. 실패해도 본문을 버리지 않는다.
        thumbnail = ""
        try:
            thumbnail = await extract_thumbnail(html, url, self._image_client)
        except Exception:
            logger.warning("thumbnail extraction failed", extra={"url": url})
        return FetchedContent(plain_text=plain_text, thumbnail_url=thumbnail)

    async def summarize(self, plain_text: str) -> SummaryOutcome:
        result = await self._summarizer.summarize(plain_text)
        if result.truncated_input:
            logger.info("summary input truncated")
        return SummaryOutcome(
            summary=result.summary,
            categories=result.categories,
            tags=result.tags,
            model_name=result.model_name,
        )
