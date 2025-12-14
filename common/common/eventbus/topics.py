from __future__ import annotations

from .core import Topic


TOPIC_POST_SUMMARY = Topic("tech-letter.post.summary")
TOPIC_POST_EMBEDDING = Topic("tech-letter.post.embedding")

ALL_TOPICS: list[Topic] = [
    TOPIC_POST_SUMMARY,
    TOPIC_POST_EMBEDDING,
]
