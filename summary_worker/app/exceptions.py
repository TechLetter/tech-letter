from __future__ import annotations


class SummaryWorkerError(Exception):
    """Base exception for all summary-worker errors."""


class RenderingError(SummaryWorkerError):
    """Failures during HTML rendering (e.g., 404/500 from ScraperAPI)."""


class ExtractionError(SummaryWorkerError):
    """Failures during plain text extraction from HTML."""


class ValidationError(SummaryWorkerError):
    """Failures during content validation (e.g., block markers)."""


class SummarizationError(SummaryWorkerError):
    """Failures during AI summarization (e.g., non-technical content)."""
