"""summary 도메인 — 렌더링·추출·검증·요약.

이 패키지만 playwright/trafilatura/bs4/Pillow에 의존한다. summary-worker
이미지에만 그 의존이 들어간다.
"""

from techletter.summary.handlers import SummaryRequestedHandler
from techletter.summary.pipeline import SummaryOutcome, SummaryPipeline
from techletter.summary.summarizer import Summarizer, SummaryResult

__all__ = [
    "Summarizer",
    "SummaryOutcome",
    "SummaryPipeline",
    "SummaryRequestedHandler",
    "SummaryResult",
]
