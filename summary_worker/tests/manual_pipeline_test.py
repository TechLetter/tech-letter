"""
수동 파이프라인 테스트 스크립트 (`manual_pipeline_test.py`).

이 스크립트는 실제 Kafka 이벤트 없이, 주어진 URL을 직접 처리하여
HTML 렌더링, 텍스트 추출, LLM 요약 과정을 순차적으로 테스트합니다.
이는 summary_worker의 핵심 파이프라인 기능 및 LLM 연동 상태를 확인하는 데 사용됩니다.

사용법:
    uv run python -m summary_worker.tests.manual_pipeline_test <url1> [url2 ...]

필수 환경 변수 (.env 파일 또는 쉘에 설정):
    SUMMARY_WORKER_LLM_PROVIDER
    SUMMARY_WORKER_LLM_MODEL_NAME
    SUMMARY_WORKER_LLM_API_KEY
    SUMMARY_WORKER_LLM_TEMPERATURE
"""

from __future__ import annotations

import logging
from typing import Sequence

from dotenv import load_dotenv

from common.llm.factory import create_chat_model

from summary_worker.app.config import load_config
from summary_worker.app.parser import extract_plain_text, extract_thumbnail
from summary_worker.app.renderer import get_renderer
from summary_worker.app.summarizer import summarize_post


logger = logging.getLogger(__name__)


def _run_single_url(url: str, *, idx: int, chat_model, renderer) -> None:
    logger.info("=== Testing URL #%d: %s ===", idx, url)

    try:
        html = renderer.render(url)
        logger.info("[OK] renderer.render len=%d", len(html))
    except Exception as exc:  # noqa: BLE001
        logger.error("[FAIL] renderer.render: %s", exc)
        return

    try:
        text = extract_plain_text(html)
        logger.info("[OK] extract_plain_text len=%d", len(text))
    except Exception as exc:  # noqa: BLE001
        logger.error("[FAIL] extract_plain_text: %s", exc)
        return

    try:
        thumbnail_url = extract_thumbnail(html, url)
        if thumbnail_url:
            logger.info("[OK] extract_thumbnail url=%s", thumbnail_url)
        else:
            logger.warning("[WARN] extract_thumbnail returned empty")
    except Exception as exc:  # noqa: BLE001
        logger.error("[FAIL] extract_thumbnail: %s", exc)
        return

    try:
        summary_result = summarize_post(chat_model=chat_model, plain_text=text)
        logger.info(
            "[OK] summarize_post: summary_len=%d, categories=%s, tags=%s",
            len(summary_result.summary),
            summary_result.categories,
            summary_result.tags,
        )
        logger.info("[OK] summarize_post: summary=%s", summary_result.summary)
    except Exception as exc:  # noqa: BLE001
        logger.error("[FAIL] summarize_post: %s", exc)


def main(argv: Sequence[str] | None = None) -> None:
    import sys

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(
            "Usage: uv run python -m summary_worker.tests.manual_pipeline_test <url1> [url2 ...]"
        )
        raise SystemExit(1)

    logging.basicConfig(level=logging.INFO)

    load_dotenv()

    app_cfg = load_config()
    chat_model = create_chat_model(app_cfg.llm)
    renderer = get_renderer(app_cfg)

    for idx, url in enumerate(argv, start=1):
        _run_single_url(url, idx=idx, chat_model=chat_model, renderer=renderer)


if __name__ == "__main__":  # pragma: no cover
    main()
