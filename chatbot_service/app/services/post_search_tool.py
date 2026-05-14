from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .content_post_client import ContentPostClient, PostItem, PostListParams


KST = ZoneInfo("Asia/Seoul")


@dataclass(slots=True)
class PostSearchRequest:
    params: PostListParams
    description: str


@dataclass(slots=True)
class PostSearchResult:
    answer: str
    sources: list[dict]
    total: int
    returned_count: int


class PostSearchTool:
    """사용자 질의를 내부 포스트 목록 조회 필터로 변환한다."""

    _post_keywords = ("포스트", "게시글", "아티클", "post", "posts", "article")
    _article_keywords = ("글",)
    _list_keywords = (
        "목록",
        "리스트",
        "리스트업",
        "찾아",
        "검색",
        "조회",
        "보여",
        "추천",
        "list",
        "search",
        "show",
        "latest",
        "recent",
    )
    _stop_filter_terms = {
        "최근",
        "지난",
        "최신",
        "관련",
        "대한",
        "포스트",
        "게시글",
        "아티클",
        "글",
        "목록",
        "리스트",
        "리스트업",
        "찾아",
        "검색",
        "조회",
        "보여",
        "추천",
        "개",
        "건",
        "일",
    }

    def __init__(
        self,
        client: ContentPostClient,
        *,
        default_page_size: int = 10,
        max_page_size: int = 20,
    ) -> None:
        self._client = client
        self._default_page_size = default_page_size
        self._max_page_size = max_page_size

    def build_request(
        self, query: str, *, now: datetime | None = None
    ) -> PostSearchRequest | None:
        normalized = query.strip()
        if not self._is_post_lookup_intent(normalized):
            return None

        current_time = now or datetime.now(timezone.utc)
        page_size = self._extract_page_size(normalized)
        published_from, published_to, date_description = self._extract_date_range(
            normalized,
            current_time,
        )
        categories = self._extract_terms(normalized, "카테고리")
        tags = self._extract_terms(normalized, "태그") + self._extract_terms(
            normalized,
            "tag",
        )
        topic_terms = self._extract_related_topic_terms(normalized)
        for term in topic_terms:
            if term not in categories:
                categories.append(term)
            if term not in tags:
                tags.append(term)

        params = PostListParams(
            page=1,
            page_size=page_size,
            categories=categories,
            tags=tags,
            blog_name=self._extract_blog_name(normalized),
            published_from=published_from,
            published_to=published_to,
            status_ai_summarized=self._extract_status_filter(
                normalized, "요약", "summarized"
            ),
            status_embedded=self._extract_status_filter(
                normalized, "임베딩", "embedded"
            ),
        )
        return PostSearchRequest(
            params=params,
            description=self._build_description(params, date_description),
        )

    def search(self, request: PostSearchRequest) -> PostSearchResult:
        result = self._client.list_posts(request.params)
        return PostSearchResult(
            answer=self._format_answer(request, result.items, result.total),
            sources=self._to_sources(result.items),
            total=result.total,
            returned_count=len(result.items),
        )

    def _is_post_lookup_intent(self, query: str) -> bool:
        lowered = query.lower()
        has_post_keyword = any(keyword in lowered for keyword in self._post_keywords)
        has_article_keyword = any(keyword in query for keyword in self._article_keywords)
        has_lookup_keyword = any(keyword in lowered for keyword in self._list_keywords)
        has_recent_window = bool(re.search(r"(최근|지난)\s*\d+\s*일", query))
        has_filter_marker = any(marker in lowered for marker in ("카테고리", "태그", "tag"))

        if has_post_keyword:
            return has_lookup_keyword or has_recent_window or has_filter_marker
        return has_article_keyword and (has_lookup_keyword or has_recent_window)

    def _extract_page_size(self, query: str) -> int:
        match = re.search(r"(\d+)\s*(?:개|건)", query)
        if not match:
            return self._default_page_size
        return max(1, min(int(match.group(1)), self._max_page_size))

    def _extract_date_range(
        self,
        query: str,
        now: datetime,
    ) -> tuple[datetime | None, datetime | None, str | None]:
        current_kst = now.astimezone(KST)
        recent_match = re.search(r"(?:최근|지난)\s*(\d+)\s*일", query)
        if recent_match:
            days = max(1, int(recent_match.group(1)))
            return (
                (current_kst - timedelta(days=days)).astimezone(timezone.utc),
                None,
                f"최근 {days}일",
            )

        if "일주일" in query or "한 주" in query or "이번 주" in query:
            return (
                (current_kst - timedelta(days=7)).astimezone(timezone.utc),
                None,
                "최근 7일",
            )

        if "오늘" in query:
            start = datetime.combine(current_kst.date(), time.min, tzinfo=KST)
            return start.astimezone(timezone.utc), None, "오늘"

        if "어제" in query:
            yesterday = current_kst.date() - timedelta(days=1)
            start = datetime.combine(yesterday, time.min, tzinfo=KST)
            end = datetime.combine(current_kst.date(), time.min, tzinfo=KST)
            return (
                start.astimezone(timezone.utc),
                end.astimezone(timezone.utc),
                "어제",
            )

        return None, None, None

    def _extract_terms(self, query: str, marker: str) -> list[str]:
        terms: list[str] = []
        patterns = [
            rf"{marker}\s*[:=]?\s*([A-Za-z0-9가-힣_.+/#-]+)",
            rf"([A-Za-z0-9가-힣_.+/#-]+)\s*{marker}",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, query, flags=re.IGNORECASE):
                terms.extend(self._split_filter_terms(match.group(1)))
        return self._dedupe(terms)

    def _extract_related_topic_terms(self, query: str) -> list[str]:
        patterns = [
            r"([A-Za-z0-9가-힣_.+/#-]+)\s*관련\s*(?:포스트|게시글|아티클|글)",
            r"(?:포스트|게시글|아티클|글)\s*중\s*([A-Za-z0-9가-힣_.+/#-]+)\s*관련",
        ]
        terms: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, query, flags=re.IGNORECASE):
                terms.extend(self._split_filter_terms(match.group(1)))
        return self._dedupe(terms)

    def _split_filter_terms(self, raw_value: str) -> list[str]:
        terms: list[str] = []
        for value in re.split(r"[,/ ]+", raw_value):
            term = value.strip(" '\"`.,")
            if not term or term in self._stop_filter_terms:
                continue
            if re.fullmatch(r"\d+", term):
                continue
            terms.append(term)
        return terms

    def _extract_blog_name(self, query: str) -> str | None:
        match = re.search(
            r"([A-Za-z0-9가-힣_.+/# -]{2,40})\s*블로그(?:에서|의|만)?",
            query,
        )
        if not match:
            return None
        candidate = match.group(1).strip(" ,")
        if candidate in {"기술", "테크", "개발", "최근", "최신"}:
            return None
        return candidate

    def _extract_status_filter(
        self, query: str, korean_keyword: str, english_keyword: str
    ) -> bool | None:
        lowered = query.lower()
        if korean_keyword in query or english_keyword in lowered:
            if "미완료" in query or "안 된" in query or "not " in lowered:
                return False
            if "완료" in query or "된" in query or english_keyword in lowered:
                return True
        return None

    def _build_description(
        self, params: PostListParams, date_description: str | None
    ) -> str:
        descriptions: list[str] = []
        if date_description:
            descriptions.append(date_description)
        if params.blog_name:
            descriptions.append(f"{params.blog_name} 블로그")
        if params.categories:
            descriptions.append("카테고리 " + ", ".join(params.categories))
        if params.tags:
            descriptions.append("태그 " + ", ".join(params.tags))
        if params.status_ai_summarized is not None:
            descriptions.append(
                "AI 요약 완료" if params.status_ai_summarized else "AI 요약 미완료"
            )
        if params.status_embedded is not None:
            descriptions.append(
                "임베딩 완료" if params.status_embedded else "임베딩 미완료"
            )
        return ", ".join(descriptions) if descriptions else "최신순"

    def _format_answer(
        self,
        request: PostSearchRequest,
        items: list[PostItem],
        total: int,
    ) -> str:
        if not items:
            return f"{request.description} 조건에 맞는 포스트를 찾지 못했습니다."

        lines = [
            f"{request.description} 조건으로 포스트를 조회했습니다. 전체 {total}개 중 최신 {len(items)}개입니다.",
            "",
        ]
        for index, item in enumerate(items, 1):
            published_date = self._format_published_date(item.published_at)
            lines.append(
                f"{index}. [{item.title}]({item.link}) - {item.blog_name}"
                f" ({published_date})"
            )
            if item.summary:
                lines.append(f"   - {self._clip(item.summary, 140)}")
            labels = item.tags or item.categories
            if labels:
                lines.append(f"   - 태그: {', '.join(labels[:5])}")
            lines.append("")
        return "\n".join(lines).strip()

    def _to_sources(self, items: list[PostItem]) -> list[dict]:
        return [
            {
                "title": item.title,
                "blog_name": item.blog_name,
                "link": item.link,
                "score": 1.0,
            }
            for item in items
        ]

    def _format_published_date(self, raw_value: str) -> str:
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return raw_value[:10] if raw_value else "발행일 없음"
        return parsed.astimezone(KST).strftime("%Y-%m-%d")

    def _clip(self, value: str, max_length: int) -> str:
        compact = re.sub(r"\s+", " ", value).strip()
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 1].rstrip() + "..."

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique_values: list[str] = []
        for value in values:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_values.append(value)
        return unique_values
