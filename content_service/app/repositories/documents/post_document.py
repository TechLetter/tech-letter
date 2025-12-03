from __future__ import annotations

from datetime import datetime

from common.models.post import AISummary, Post, StatusFlags
from common.mongo.types import BaseDocument, PyObjectId


class PostDocument(BaseDocument):
    """MongoDB posts 컬렉션 도큐먼트 모델."""

    status: StatusFlags
    view_count: int
    blog_id: PyObjectId
    blog_name: str
    title: str
    link: str
    published_at: datetime
    # 도큐먼트 레벨에서는 필드가 누락될 수 있으므로 기본값을 빈 문자열로 둔다.
    # - Mongo projection에서 제외되거나
    # - 도메인 Post -> Document 변환 시 필드가 비어 있어도 ValidationError가 발생하지 않도록 한다.
    thumbnail_url: str | None = ""
    rendered_html: str | None = ""
    plain_text: str | None = ""
    aisummary: AISummary

    @classmethod
    def from_domain(cls, post: Post) -> "PostDocument":
        data = post.model_dump(by_alias=True)
        _id = data.pop("id", None)
        if _id is not None:
            data["_id"] = _id

        return cls.model_validate(data)
