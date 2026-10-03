"""summary 도메인 — 원문 렌더링·추출·검증, 쉽게 읽기 생성 잡, 주제 목록.

이 패키지만 playwright/trafilatura/bs4/Pillow에 의존한다. summary-worker
이미지에만 그 의존이 들어간다. (예전 200자 요약 생성기는 2026-10-04에 지웠다 — 새 글은
쉽게 읽기를 바로 만든다.)
"""

from techletter.summary.handlers import SummaryRequestedHandler
from techletter.summary.pipeline import ContentPipeline

__all__ = ["ContentPipeline", "SummaryRequestedHandler"]
