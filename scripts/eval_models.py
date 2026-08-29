"""무료 모델 요약 품질 실측 (ADR-0008 §6).

선호 목록(`SUMMARY_MODEL_PREFERENCE`, `CHAT_MODEL_PREFERENCE`)을 바꾸기 전에
돌린다. 무료 모델은 몇 주 단위로 생겼다 없어지므로 목록은 실측으로만 정한다.

    OPENROUTER_API_KEY=... uv run python scripts/eval_models.py --limit 3
    OPENROUTER_API_KEY=... uv run python scripts/eval_models.py --models a:free,b:free

샘플은 운영 DB에서 요약이 끝난 포스트를 가져온다(`--mongo-uri`). 없으면
`tests/fixtures/seed/prod_content_sample.json`의 본문 조각으로 대신한다.

**실측이 답하지 못하는 것**: 사실 정확성. 실측에서 `north-mini-code:free`가
글의 결론을 정반대로 요약했지만 어떤 자동 점수로도 걸러지지 않았다. 그래서
선호 목록은 사람이 읽고 정한다 — 이 스크립트는 후보를 줄여 줄 뿐이다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 8000
TARGET_CHARS = 200
TOLERANCE = 20
MAX_TAGS = 7

# 2026-08-28 실측 시점의 후보. 최신 목록은 scouter나 OpenRouter 모델 API로 받는다.
DEFAULT_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m3:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "z-ai/glm-5.2:free",
    "dots-studio/dots-3-note-preview:free",
]


def system_prompt() -> str:
    from techletter.summary.summarizer import SYSTEM_INSTRUCTION

    return SYSTEM_INSTRUCTION


async def load_samples(mongo_uri: str | None, limit: int) -> list[dict]:
    """운영 DB에서 요약된 포스트를 뽑는다. 접속이 안 되면 픽스처로 떨어진다."""
    if mongo_uri:
        try:
            from pymongo import AsyncMongoClient

            client = AsyncMongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            db = client.get_default_database() or client["techletter"]
            cursor = db["posts"].find(
                {"status.ai_summarized": True, "plain_text": {"$ne": ""}},
                projection={"title": 1, "plain_text": 1},
                limit=limit,
            )
            samples = [
                {"title": doc.get("title", ""), "text": doc.get("plain_text", "")[:12000]}
                async for doc in cursor
            ]
            await client.close()
            if samples:
                return samples
        except Exception as exc:
            print(f"[warn] Mongo 샘플을 못 가져왔다: {exc}", file=sys.stderr)

    path = ROOT / "tests" / "fixtures" / "seed" / "prod_content_sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"title": doc["title"], "text": doc.get("plain_text", "")}
        for doc in data["posts"][:limit]
        if doc.get("plain_text")
    ]


async def call_model(client, model: str, system: str, text: str) -> tuple[dict | None, float, str]:
    """(파싱된 JSON, 초, 오류) — 실패해도 예외를 올리지 않는다."""
    from techletter.core.llm.chat import extract_json

    started = time.monotonic()
    try:
        response = await client.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "max_tokens": MAX_TOKENS,
                # 무료 모델은 전부 추론 모델이다. 이걸 빼면 절반이 빈 응답을 준다.
                "reasoning": {"exclude": True},
            },
            timeout=180.0,
        )
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            return None, elapsed, f"HTTP {response.status_code}"
        content = response.json()["choices"][0]["message"]["content"]
        return extract_json(content), elapsed, ""
    except Exception as exc:
        return None, time.monotonic() - started, f"{type(exc).__name__}: {exc}"


def score(payload: dict) -> dict:
    """계약 준수 여부만 본다. 사실 정확성은 사람이 읽어야 한다."""
    from techletter.summary.summarizer import normalize_categories, normalize_tags

    summary = str(payload.get("summary") or "")
    tags = payload.get("tags") or []
    categories = payload.get("categories") or []
    return {
        "chars": len(summary),
        "length_ok": abs(len(summary) - TARGET_CHARS) <= TOLERANCE,
        "tag_count": len(tags) if isinstance(tags, list) else 0,
        "tags_ok": isinstance(tags, list) and 3 <= len(tags) <= MAX_TAGS,
        "categories_ok": normalize_categories(categories)
        == [c for c in categories if isinstance(c, str)][:3],
        "tags_deduped": normalize_tags(tags, MAX_TAGS) == tags,
        "summary": summary,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--limit", type=int, default=2, help="샘플 포스트 수")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI"))
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = parser.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        print("OPENROUTER_API_KEY 가 필요하다.", file=sys.stderr)
        return 2

    import httpx

    samples = await load_samples(args.mongo_uri, args.limit)
    if not samples:
        print("샘플이 없다.", file=sys.stderr)
        return 2
    system = system_prompt()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    results: list[dict] = []

    async with httpx.AsyncClient() as client:
        for model in models:
            runs = []
            for sample in samples:
                payload, elapsed, error = await call_model(client, model, system, sample["text"])
                runs.append(
                    {
                        "title": sample["title"][:50],
                        "seconds": round(elapsed, 1),
                        "error": error,
                        **(score(payload) if payload else {}),
                    }
                )
                status = "ok" if payload else (error or "json 파싱 실패")
                print(f"{model:<48} {elapsed:6.1f}s  {status}")
            ok = [r for r in runs if not r.get("error") and "chars" in r]
            results.append(
                {
                    "model": model,
                    "success_rate": round(len(ok) / len(runs), 2),
                    "median_seconds": round(statistics.median(r["seconds"] for r in runs), 1),
                    "length_ok": sum(r.get("length_ok", False) for r in ok),
                    "tags_ok": sum(r.get("tags_ok", False) for r in ok),
                    "runs": runs,
                }
            )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    print("\n| 모델 | 성공률 | 중앙 지연 | 길이 준수 | 태그 준수 |")
    print("|---|---|---|---|---|")
    for row in sorted(results, key=lambda r: (-r["success_rate"], r["median_seconds"])):
        print(
            f"| `{row['model']}` | {row['success_rate']:.0%} | {row['median_seconds']}s "
            f"| {row['length_ok']}/{len(samples)} | {row['tags_ok']}/{len(samples)} |"
        )
    print("\n요약문을 **직접 읽어 보라**. 실측에서 한 모델이 결론을 정반대로 썼다.")
    for row in results:
        for run in row["runs"]:
            if run.get("summary"):
                print(f"\n[{row['model']}] {run['title']}\n  {run['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
