from __future__ import annotations

from .core import Topic


TOPIC_POST_EVENTS = Topic("tech-letter.post.events")

ALL_TOPICS: list[Topic] = [
    TOPIC_POST_EVENTS,
]
