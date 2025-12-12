from __future__ import annotations

from .core import Topic


TOPIC_POST_SUMMARY = Topic("tech-letter.post.summary")

ALL_TOPICS: list[Topic] = [
    TOPIC_POST_SUMMARY,
]
