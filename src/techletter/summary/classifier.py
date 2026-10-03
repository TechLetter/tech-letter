"""주제 재분류. 주제 목록을 바꾸면 `techletter backfill topics`가 쓴다.

본문 대신 제목·요약·키워드만 보내 여러 건을 한 번에 분류한다(1,900건을 한 건씩 부르면
무료 한도로 며칠 걸린다). 새 글의 주제는 쉽게 읽기 생성이 함께 정한다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from techletter.core.logging import get_logger
from techletter.summary.topics import normalize_topics, topic_prompt_lines

if TYPE_CHECKING:  # pragma: no cover
    from techletter.core.llm.chat import LlmGateway

__all__ = ["TOPIC_CLASSIFY_INSTRUCTION", "TopicClassifier"]

logger = get_logger(__name__)

TOPIC_CLASSIFY_INSTRUCTION = f"""\
You classify tech blog posts into topics.
Input is a JSON array of posts with id, title, blog, summary and keywords.
Return ONLY a JSON object: {{"results": [{{"id": "...", "topics": ["slug", ...]}}]}}
with one entry per input post.
Pick 1-3 topic slugs per post from the list below, most central first.
Choose by what the post is mainly about, not by technologies mentioned in passing.
Add a second or third topic only when a substantial part of the post is about it
(e.g. an AI-based fraud detector -> the AI topic and "security"; a team onboarding
retrospective -> "culture" and the team's field). Use "other" only when nothing fits.

Topics (slug | name | definition):
{topic_prompt_lines()}
"""
# 추론 토큰을 쓰는 모델이 결과를 쓰기도 전에 한도를 다 쓰지 않게 넉넉히 준다.
_CLASSIFY_MAX_TOKENS = 8000


class TopicClassifier:
    def __init__(self, llm: LlmGateway) -> None:
        self._llm = llm

    async def classify_topics(self, posts: list[dict[str, Any]]) -> dict[str, list[str]]:
        """`{id, title, blog, summary, keywords}` 목록 → id별 주제 이름.

        모델이 빠뜨린 글은 결과에 없다. 호출한 쪽이 다음에 다시 시도한다.
        """
        payload, model_id = await self._llm.complete_json(
            "summary",
            TOPIC_CLASSIFY_INSTRUCTION,
            json.dumps(posts, ensure_ascii=False),
            max_tokens=_CLASSIFY_MAX_TOKENS,
        )
        wanted = {str(post["id"]) for post in posts}
        results: dict[str, list[str]] = {}
        for row in payload.get("results") or []:
            if not isinstance(row, dict):
                continue
            post_id = str(row.get("id") or "")
            if post_id in wanted:
                results[post_id] = normalize_topics(row.get("topics"))
        logger.info(
            "topics classified",
            extra={"model": model_id, "asked": len(posts), "answered": len(results)},
        )
        return results
