from __future__ import annotations

from common.models.blog import Blog
from common.mongo.types import BaseDocument


class BlogDocument(BaseDocument):
    """MongoDB blogs 컬렉션 도큐먼트 모델."""

    name: str
    url: str
    rss_url: str
    blog_type: str

    @classmethod
    def from_domain(cls, blog: Blog) -> "BlogDocument":
        data = blog.model_dump(by_alias=True)
        _id = data.pop("id", None)
        if _id is not None:
            data["_id"] = _id
        return cls.model_validate(data)
