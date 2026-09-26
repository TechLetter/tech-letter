"""어휘 색인 — 토큰화와 BM25 가중치."""

from __future__ import annotations

import zlib

import pytest

from techletter.search.lexical import (
    BM25_K1,
    document_vector,
    query_vector,
    token_index,
    tokenize,
)


# ── 토큰화 ──────────────────────────────────────────────────────────
def test_latin_words_are_lowercased_and_kept_whole() -> None:
    assert tokenize("vLLM K8s CDC") == ["vllm", "k8s", "cdc"]


def test_single_latin_letters_are_dropped() -> None:
    assert tokenize("a b go") == ["go"]


def test_punctuation_splits_words() -> None:
    assert tokenize("node.js/c++") == ["node", "js"]


def test_hangul_runs_become_bigrams() -> None:
    assert tokenize("카프카를") == ["카프", "프카", "카를"]


def test_short_hangul_runs_are_also_kept_whole() -> None:
    """세 글자 이하 어절은 통째로도 넣는다. 두 글자는 2-gram과 같아 한 번만."""
    assert tokenize("카카오") == ["카카", "카오", "카카오"]
    assert tokenize("쿠팡") == ["쿠팡"]
    assert tokenize("및") == ["및"]


def test_mixed_scripts_split_at_the_boundary() -> None:
    assert tokenize("CDC를 도입") == ["cdc", "를", "도입"]


def test_full_width_letters_are_normalized() -> None:
    assert tokenize("ＡＰＩ") == ["api"]


def test_empty_text_has_no_tokens() -> None:
    assert tokenize("") == []
    assert tokenize("!!! ...") == []


def test_token_index_is_a_stable_crc32() -> None:
    """프로세스마다 달라지는 `hash()`가 아니어야 색인과 질의가 맞는다."""
    assert token_index("kafka") == zlib.crc32(b"kafka")
    assert 0 <= token_index("카프") < 2**32


# ── 가중치 ──────────────────────────────────────────────────────────
def weight_of(fields: dict[str, str], token: str, **kwargs) -> float:
    doc = document_vector(fields, **kwargs)
    return dict(zip(doc.indices, doc.values, strict=True)).get(token_index(token), 0.0)


def test_indices_are_unique_and_sorted() -> None:
    doc = document_vector({"title": "kafka kafka", "summary": "kafka stream"})

    assert doc.indices == sorted(set(doc.indices))
    assert len(doc.values) == len(doc.indices)


def test_title_outweighs_summary() -> None:
    in_title = weight_of({"title": "kafka", "summary": "stream"}, "kafka")
    in_summary = weight_of({"title": "stream", "summary": "kafka"}, "kafka")

    assert in_title > in_summary


def test_tags_outweigh_categories() -> None:
    in_tags = weight_of({"tags": "kafka", "categories": "stream"}, "kafka")
    in_categories = weight_of({"tags": "stream", "categories": "kafka"}, "kafka")

    assert in_tags > in_categories


def test_term_frequency_saturates_below_k1_plus_one() -> None:
    once = weight_of({"summary": "kafka"}, "kafka", avg_doc_length=1)
    many = weight_of({"summary": "kafka " * 50}, "kafka", avg_doc_length=50)

    assert many > once
    assert many < BM25_K1 + 1


def test_longer_documents_weigh_a_term_less() -> None:
    short = weight_of({"summary": "kafka stream"}, "kafka")
    long = weight_of({"summary": "kafka " + "filler " * 300}, "kafka")

    assert short > long


def test_bm25_value_matches_the_formula() -> None:
    # tf=1, 문서 길이=평균 → 1·2.2 / (1 + 1.2) = 1.0
    assert weight_of({"summary": "kafka"}, "kafka", avg_doc_length=1) == pytest.approx(1.0)


def test_query_tokens_are_unique_with_weight_one() -> None:
    doc = query_vector("kafka Kafka 카프카")

    assert len(doc.indices) == len(set(doc.indices)) == 4  # kafka, 카프, 프카, 카프카
    assert doc.values == [1.0] * 4
