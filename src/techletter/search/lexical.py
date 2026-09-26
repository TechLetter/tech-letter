"""어휘(BM25) 검색용 토큰화와 가중치.

형태소 분석기를 들이지 않는다. 한국어는 글자 2-gram으로 자르면 조사가 붙은
어절("카프카를")도 "카프"·"프카"로 맞고, 영문 기술 용어("vllm", "k8s", "cdc")는
단어 그대로 맞는다. 요약·제목 수준의 짧은 문서에는 이 정도로 충분하다.

점수 계산은 Qdrant와 나눈다. 문서 쪽 값은 BM25의 tf 포화·길이 정규화까지
여기서 계산해 넣고, IDF는 컬렉션의 `modifier=IDF`가 질의 시점에 곱한다.
질의 쪽 값은 토큰마다 1이다.
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.db.qdrant import LexicalPoint
from techletter.core.time import to_iso_z

if TYPE_CHECKING:  # pragma: no cover
    from techletter.content.models import Post

__all__ = [
    "AVG_DOC_LENGTH",
    "BM25_B",
    "BM25_K1",
    "FIELD_WEIGHTS",
    "SparseDoc",
    "document_length",
    "document_vector",
    "lexical_payload",
    "lexical_point",
    "post_fields",
    "query_vector",
    "token_index",
    "tokenize",
]

BM25_K1 = 1.2
BM25_B = 0.75
AVG_DOC_LENGTH = 170.0
"""가중치를 곱한 문서 길이(토큰 수)의 평균. 운영 문서 샘플(요약 200자 안팎)로
잰 값이다. 문서가 들어올 때마다 평균을 다시 재면 먼저 넣은 문서와 기준이
어긋나므로 상수로 둔다. `techletter backfill lexical --dry-run`이 코퍼스 실측값을
보여 준다 — 크게 벌어지면 이 값을 고치고 다시 백필한다."""

FIELD_WEIGHTS: dict[str, float] = {
    "title": 3.0,
    "tags": 2.0,
    "categories": 1.0,
    "blog_name": 1.0,
    "summary": 1.0,
}

# 라틴 문자(악센트 포함)·숫자 묶음과 한글 음절 묶음. 나머지 문자는 구분자다.
_TOKEN_RUN = re.compile(r"[0-9a-z\u00c0-\u024f]+|[\uac00-\ud7a3]+")
_HANGUL_MAX_WHOLE = 3


def _is_hangul(run: str) -> bool:
    return "\uac00" <= run[0] <= "\ud7a3"


def tokenize(text: str) -> list[str]:
    """소문자화한 뒤 토큰으로 자른다. 순서와 중복을 유지한다(tf 계산용)."""
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    tokens: list[str] = []
    for run in _TOKEN_RUN.findall(normalized):
        if _is_hangul(run):
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
            # 짧은 어절은 통째로도 넣는다. "카카오" 같은 세 글자 이름이 더 정확히 맞고,
            # 한 글자 단어도 잃지 않는다. 두 글자는 2-gram과 같아 다시 넣지 않는다.
            if len(run) <= _HANGUL_MAX_WHOLE and len(run) != 2:
                tokens.append(run)
        elif len(run) > 1:
            tokens.append(run)
    return tokens


def token_index(token: str) -> int:
    """토큰 → uint32. 프로세스·버전이 달라도 같아야 하므로 `hash()`를 쓰지 않는다."""
    return zlib.crc32(token.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SparseDoc:
    indices: list[int]
    values: list[float]


def _weighted_tf(fields: dict[str, str]) -> dict[int, float]:
    """필드 가중치를 곱한 tf. 해시가 겹친 토큰은 한 차원으로 합친다."""
    tf: dict[int, float] = {}
    for name, text in fields.items():
        weight = FIELD_WEIGHTS.get(name, 1.0)
        for token in tokenize(text):
            index = token_index(token)
            tf[index] = tf.get(index, 0.0) + weight
    return tf


def document_length(fields: dict[str, str]) -> float:
    return sum(_weighted_tf(fields).values())


def document_vector(
    fields: dict[str, str],
    *,
    avg_doc_length: float = AVG_DOC_LENGTH,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> SparseDoc:
    """BM25의 tf 항: tf·(k1+1) / (tf + k1·(1 − b + b·dl/avgdl))."""
    tf = _weighted_tf(fields)
    length = sum(tf.values())
    norm = k1 * (1 - b + b * length / avg_doc_length)
    indices = sorted(tf)
    return SparseDoc(
        indices=indices,
        values=[tf[i] * (k1 + 1) / (tf[i] + norm) for i in indices],
    )


def query_vector(query: str) -> SparseDoc:
    indices = sorted({token_index(token) for token in tokenize(query)})
    return SparseDoc(indices=indices, values=[1.0] * len(indices))


def post_fields(post: Post) -> dict[str, str]:
    summary = post.aisummary
    return {
        "title": post.title,
        "tags": " ".join(summary.tags) if summary else "",
        "categories": " ".join(summary.categories) if summary else "",
        "blog_name": post.blog_name,
        "summary": (summary.summary or "") if summary else "",
    }


def lexical_payload(post: Post) -> dict[str, object]:
    """필터와 자동완성에 쓰는 값만 싣는다. 자동완성은 Mongo를 거치지 않는다."""
    return {
        "post_id": str(post.id),
        "blog_id": str(post.blog_id) if post.blog_id else None,
        "categories": post.aisummary.categories if post.aisummary else [],
        "published_at": to_iso_z(post.published_at),
        "title": post.title,
        "blog_name": post.blog_name,
        "link": post.link,
    }


def lexical_point(post: Post, *, avg_doc_length: float = AVG_DOC_LENGTH) -> LexicalPoint:
    doc = document_vector(post_fields(post), avg_doc_length=avg_doc_length)
    return LexicalPoint(
        post_id=str(post.id),
        indices=doc.indices,
        values=doc.values,
        payload=lexical_payload(post),
    )
