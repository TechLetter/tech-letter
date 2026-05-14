from __future__ import annotations

from datetime import datetime, timezone

from chatbot_service.app.services.content_post_client import (
    PostItem,
    PostListParams,
    PostListResult,
)
from chatbot_service.app.services.post_search_tool import PostSearchTool


class FakeContentPostClient:
    def __init__(self) -> None:
        self.params: PostListParams | None = None

    def list_posts(self, params: PostListParams) -> PostListResult:
        self.params = params
        return PostListResult(
            total=1,
            items=[
                PostItem(
                    id="post-1",
                    title="React Server Components",
                    link="https://example.com/rsc",
                    blog_name="Example Blog",
                    published_at="2026-05-13T00:00:00+00:00",
                    summary="React Server Components 요약입니다.",
                    categories=["Frontend"],
                    tags=["React"],
                )
            ],
        )


def test_build_request_extracts_recent_days_and_limit() -> None:
    tool = PostSearchTool(FakeContentPostClient())
    now = datetime(2026, 5, 14, 3, 0, tzinfo=timezone.utc)

    request = tool.build_request("최근 7일 포스트 5개 리스트업해줘", now=now)

    assert request is not None
    assert request.params.page_size == 5
    assert request.params.published_from is not None
    assert request.params.published_from.date().isoformat() == "2026-05-07"
    assert request.description == "최근 7일"


def test_build_request_extracts_related_topic_as_filters() -> None:
    tool = PostSearchTool(FakeContentPostClient())

    request = tool.build_request("React 관련 포스트 찾아줘")

    assert request is not None
    assert request.params.categories == ["React"]
    assert request.params.tags == ["React"]


def test_build_request_ignores_regular_explanation_question() -> None:
    tool = PostSearchTool(FakeContentPostClient())

    request = tool.build_request("React Server Components 동작 원리를 설명해줘")

    assert request is None


def test_search_formats_post_list_answer_and_sources() -> None:
    client = FakeContentPostClient()
    tool = PostSearchTool(client)
    request = tool.build_request("React 관련 포스트 찾아줘")

    assert request is not None
    result = tool.search(request)

    assert client.params is request.params
    assert "React 관련" not in result.answer
    assert "[React Server Components](https://example.com/rsc)" in result.answer
    assert result.sources == [
        {
            "title": "React Server Components",
            "blog_name": "Example Blog",
            "link": "https://example.com/rsc",
            "score": 1.0,
        }
    ]
