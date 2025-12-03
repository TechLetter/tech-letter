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
    thumbnail_url: str
    rendered_html: str
    aisummary: AISummary

    @classmethod
    def from_domain(cls, post: Post) -> "PostDocument":
        data = post.model_dump(by_alias=True)
        _id = data.pop("id", None)
        if _id is not None:
            data["_id"] = _id

        return cls.model_validate(data)
