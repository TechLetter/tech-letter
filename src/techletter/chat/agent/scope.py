"""질문에서 범위(블로그·기간·개수·목록 여부)와 후속 참조를 코드로 읽는다.

예전에는 LLM 플래너가 이것을 JSON으로 뽑았다. 그러다 서비스 이름을 블로그로
착각하거나, 없는 태그를 지어내 관련 글이 있는데도 "찾지 못했습니다"로 끝났다
(2026-09-27 기준선 20문항 중 3건). 확인할 수 있는 값만 코드로 읽는다. 나머지는
검색이 맡는다.

- **블로그**: "카카오 블로그", "토스의 글"처럼 명시하면 그 블로그로 좁힌다.
  이름만 나오면("AWS Lambda 사례") 좁히지 않고 그 블로그 글을 앞으로 올린다.
  "라인"은 "파이프라인"에, "AWS"는 기술 이름에도 나오기 때문이다.
- **기간**: 한국 시간 기준 "이번 달", "지난주", "최근 7일", "2026년 9월" 등.
- **목록**: "목록", "리스트"이거나, "글/포스트 N개 보여줘"처럼 글을 나열해 달라는 말.
  설명·정리를 원하면 목록이 아니다.
- **후속 참조**: "거기서", "그 글" 같은 말이 있으면 직전 답의 출처 안에서 답한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from techletter.core.time import utcnow
from techletter.summary.topics import TOPIC_NAMES

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

__all__ = [
    "KST",
    "BlogRef",
    "Scope",
    "is_reference",
    "match_blog",
    "match_topics",
    "parse_period",
    "read_scope",
]

KST = ZoneInfo("Asia/Seoul")
DEFAULT_LIST_LIMIT = 10
MAX_LIST_LIMIT = 20

# 흔히 쓰는 다른 이름. 키는 운영 블로그 이름이다.
BLOG_ALIASES: dict[str, tuple[str, ...]] = {
    "당근마켓": ("당근",),
    "카카오": ("kakao",),
    "네이버": ("naver",),
    "라인": ("line",),
    "토스": ("toss",),
    "우아한형제들": ("배민", "우아한 형제들"),
    "올리브영": ("cj올리브영",),
}

_BLOG_MARKER = re.compile(
    r"^\s*(?:기술\s*블로그|테크\s*블로그|블로그|tech\s*blog|engineering|techblog"
    r"|에서\s*(?:쓴|올린|작성|나온|발행)|에\s*(?:올라온|올린|나온|있는\s*글)|가\s*쓴|이\s*쓴|글|포스트)",
    re.I,
)
_LIST = re.compile(r"목록|리스트|리스트업|list", re.I)
_LIST_ASK = re.compile(
    r"(?:글|포스트|아티클|게시물)\s*(?:\d+\s*(?:개|편|건)\s*)?(?:만\s*)?(?:보여|알려|뽑아|추천)"
)
_EXPLAIN = re.compile(r"정리|요약|설명|비교|차이|어떻게|왜|방법|사례|분석|내용")
_COUNT = re.compile(r"(\d{1,2})\s*(?:개|편|건)")
_REFERENCE = re.compile(
    r"거기|그\s*글|그\s*포스트|그\s*중|그중|이\s*글|위\s*글|위에서|방금|해당\s*글|그거|그것|"
    r"첫\s*번째|두\s*번째|세\s*번째|\d\s*번\s*글|앞의|앞에서"
)
_RELEASE = re.compile(r"다른\s*(?:글|포스트|블로그|사례|회사|곳|기업)|말고|빼고|제외")
_EXCLUDE = re.compile(r"말고|빼고|제외")
# 기간 표현은 글을 묻는 문맥에서만 발행일 필터로 쓴다. "오늘 서울 날씨"는 기간 질문이 아니다.
_POST_CONTEXT = re.compile(
    r"글|포스트|아티클|게시물|블로그|올라온|올린|발행|목록|리스트|소식|업데이트|나온"
)
_WORD_START = r"(?<![0-9a-z가-힣])"
_NOT_BLOG_NAMES = frozenset({"기술", "테크", "이", "그", "이런", "여러", "개인", "회사"})
# "OO 블로그"라고 했는데 OO가 모으는 블로그에 없을 때 알린다.
_NAMED_BLOG = re.compile(r"([0-9A-Za-z가-힣.]+)\s*(?:\([^)]*\))?\s*(?:기술\s*|테크\s*)?블로그")


@dataclass(frozen=True, slots=True)
class BlogRef:
    id: str
    name: str


@dataclass(slots=True)
class Scope:
    blog: BlogRef | None = None
    """명시된 블로그. 이 블로그 글만 쓴다."""
    boost_blog: BlogRef | None = None
    """이름만 나온 블로그. 좁히지 않고 이 블로그 글을 앞으로 올린다."""
    published_from: datetime | None = None
    published_to: datetime | None = None
    period_label: str = ""
    topics: list[str] = field(default_factory=list)
    """목록 요청에서만 쓰는 주제 필터."""
    is_list: bool = False
    limit: int = DEFAULT_LIST_LIMIT
    exclude_blogs: list[BlogRef] = field(default_factory=list)
    """"카카오 말고"처럼 빼 달라고 한 블로그."""
    unknown_blog: str = ""
    """"OO 블로그"라고 했지만 모으지 않는 블로그 이름."""

    def has_filter(self) -> bool:
        return bool(self.blog or self.published_from or self.published_to)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def match_blog(query: str, blogs: Iterable[BlogRef]) -> tuple[BlogRef | None, BlogRef | None]:
    """(명시된 블로그, 이름만 나온 블로그). 이름이 긴 것부터 본다("카카오페이" > "카카오")."""
    text = _norm(query)
    names: list[tuple[str, BlogRef]] = []
    for blog in blogs:
        names.append((_norm(blog.name), blog))
        names.extend((_norm(alias), blog) for alias in BLOG_ALIASES.get(blog.name, ()))
    names.sort(key=lambda item: len(item[0]), reverse=True)

    boost: BlogRef | None = None
    for name, blog in names:
        if len(name) < 2:
            continue
        # 단어 시작에서만 찾는다: "파이프라인"의 "라인"은 블로그가 아니다.
        for match in re.finditer(r"(?<![0-9a-z가-힣])" + re.escape(name), text):
            rest = text[match.end() :]
            if rest[:1].isalnum() and rest[:1].isascii():
                continue  # "lineage"의 "line"
            if _BLOG_MARKER.match(rest):
                return blog, None
            if boost is None:
                boost = blog
    return None, boost


def match_topics(query: str) -> list[str]:
    """주제 이름의 조각("쿠버네티스", "보안")이 질문에 있으면 그 주제."""
    text = _norm(query)
    found: list[str] = []
    for name in TOPIC_NAMES:
        parts = [p for p in re.split(r"[·/ ]", name.lower()) if len(p) >= 2]
        if any(part in text for part in parts):
            found.append(name)
    return found


def _kst_day(dt: datetime) -> datetime:
    return dt.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=KST)


def _next_month(dt: datetime) -> datetime:
    return _month_start(dt.year + (dt.month == 12), dt.month % 12 + 1)


def parse_period(  # noqa: PLR0911 — 표현마다 한 줄씩 판정한다
    query: str, now: datetime | None = None
) -> tuple[datetime | None, datetime | None, str]:
    """(시작, 끝, 설명). 끝은 포함 경계다(목록 API의 `$lte`와 같다). 없으면 (None, None, "")."""
    now = (now or utcnow()).astimezone(KST)
    today = _kst_day(now)
    text = query.replace(" ", "")
    end_of = lambda start: start - timedelta(microseconds=1)  # noqa: E731

    if m := re.search(r"(20\d{2})년(\d{1,2})월", text):
        start = _month_start(int(m.group(1)), int(m.group(2)))
        return start, end_of(_next_month(start)), f"{m.group(1)}년 {m.group(2)}월"
    if m := re.search(r"(?:최근|지난)(\d{1,3})(일|주|개월|달)", text):
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"일": 1, "주": 7, "개월": 30, "달": 30}[unit]
        return today - timedelta(days=days - 1), now, f"최근 {n}{unit}"
    # "오늘의집", "오늘날"은 날짜가 아니다.
    if re.search(r"오늘(?!의|날)", text):
        return today, now, "오늘"
    if re.search(r"어제(?!오늘)", text):
        return today - timedelta(days=1), end_of(today), "어제"
    week = today - timedelta(days=today.weekday())
    if re.search(r"이번주|금주", text):
        return week, now, "이번 주"
    if re.search(r"지난주|저번주", text):
        return week - timedelta(days=7), end_of(week), "지난주"
    month = _month_start(today.year, today.month)
    if re.search(r"이번달|이달|금월", text):
        return month, now, "이번 달"
    if re.search(r"지난달|저번달|전월", text):
        prev = _month_start(today.year - (today.month == 1), (today.month - 2) % 12 + 1)
        return prev, end_of(month), "지난달"
    if re.search(r"올해|금년", text):
        return datetime(today.year, 1, 1, tzinfo=KST), now, "올해"
    if re.search(r"작년|지난해", text):
        return (
            datetime(today.year - 1, 1, 1, tzinfo=KST),
            end_of(datetime(today.year, 1, 1, tzinfo=KST)),
            "작년",
        )
    if m := re.search(r"(?<!\d)(\d{1,2})월(?:에|의|달|글|$)", text):
        month_n = int(m.group(1))
        if 1 <= month_n <= 12:
            year = today.year if month_n <= today.month else today.year - 1
            start = _month_start(year, month_n)
            return start, end_of(_next_month(start)), f"{year}년 {month_n}월"
    return None, None, ""


def is_reference(query: str) -> bool:
    """직전 답의 글을 가리키는가. "다른 글도"는 범위를 푼다."""
    return bool(_REFERENCE.search(query)) and not _RELEASE.search(query)


def _mentioned(query: str, blogs: list[BlogRef]) -> list[BlogRef]:
    """질문에 이름이 나온 블로그. 긴 이름부터 보고, 이미 잡힌 자리 안의 짧은 이름은 세지 않는다
    ("카카오페이"의 "카카오")."""
    text = _norm(query)
    names = sorted(
        (
            (n, blog)
            for blog in blogs
            for n in (_norm(blog.name), *(_norm(a) for a in BLOG_ALIASES.get(blog.name, ())))
            if len(n) >= 2
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    taken: list[tuple[int, int]] = []
    found: list[BlogRef] = []
    for name, blog in names:
        for m in re.finditer(_WORD_START + re.escape(name), text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            if blog not in found:
                found.append(blog)
    return found


def read_scope(query: str, blogs: Iterable[BlogRef], now: datetime | None = None) -> Scope:
    blogs = list(blogs)
    exclude: list[BlogRef] = []
    if _EXCLUDE.search(query):
        # "카카오, 당근마켓 말고 다른 회사" — 이름이 나온 블로그는 좁히지도 올리지도 않고 뺀다.
        exclude = _mentioned(query, blogs)
        blog, boost = None, None
    else:
        blog, boost = match_blog(query, blogs)
        if len(_mentioned(query, blogs)) >= 2:
            # 여러 블로그(또는 블로그 이름과 같은 기술 이름)가 나오면 비교 질문이다.
            # 한쪽으로 좁히거나 올리지 않는다("인프랩이 AWS Client VPN에서…", "Datadog과 Uber").
            blog, boost = None, None
    unknown = ""
    if blog is None and (m := _NAMED_BLOG.search(query)):
        name = m.group(1)
        known = {_norm(b.name) for b in blogs} | {
            _norm(a) for b in blogs for a in BLOG_ALIASES.get(b.name, ())
        }
        if _norm(name) not in known and _norm(name) not in {
            "기술",
            "테크",
            "이",
            "그",
            "이런",
            "여러",
        }:
            unknown = name
    is_list = bool(_LIST.search(query)) or (
        bool(_LIST_ASK.search(query)) and not _EXPLAIN.search(query)
    )
    start, end, label = (
        parse_period(query, now) if is_list or _POST_CONTEXT.search(query) else (None, None, "")
    )
    limit = DEFAULT_LIST_LIMIT
    if m := _COUNT.search(query):
        limit = max(1, min(int(m.group(1)), MAX_LIST_LIMIT))
    return Scope(
        blog=blog,
        boost_blog=boost,
        published_from=start,
        published_to=end,
        period_label=label,
        topics=match_topics(query) if is_list else [],
        is_list=is_list,
        limit=limit,
        exclude_blogs=exclude,
        unknown_blog=unknown,
    )
