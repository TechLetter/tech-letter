"""`techletter` 단일 진입점.

프로세스 4종이 전부 여기서 나온다.
    techletter api               HTTP 서버
    techletter worker            RSS 스케줄러 · 잡 컨슈머 · 유지보수
    techletter summary-worker    요약 파이프라인 (Playwright)
    techletter embedding-worker  임베딩 파이프라인
    techletter all               api + worker (로컬 개발용)

운영 명령(`jobs`, `backfill`)도 같은 바이너리에 있다.
"""

from __future__ import annotations

import asyncio
from itertools import combinations
from typing import TYPE_CHECKING, Any

import typer

from techletter import __version__
from techletter.content.links import normalize_link

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Coroutine

    from techletter.container import Container
    from techletter.content.models import Post

app = typer.Typer(
    name="techletter",
    help="Tech-Letter 서비스 실행·운영 도구",
    no_args_is_help=True,
    add_completion=False,
)
jobs_app = typer.Typer(help="잡 큐 조회·재처리", no_args_is_help=True)
backfill_app = typer.Typer(help="누락분 백필", no_args_is_help=True)
settings_app = typer.Typer(help="설정 점검", no_args_is_help=True)
app.add_typer(jobs_app, name="jobs")
app.add_typer(backfill_app, name="backfill")
app.add_typer(settings_app, name="settings")


def _with_container(
    body: Callable[[Container], Coroutine[Any, Any, None]], *, create_indexes: bool = False
) -> None:
    """컨테이너를 열고 닫는 일회성 명령용 래퍼."""

    async def run() -> None:
        from techletter.container import Container  # noqa: PLC0415
        from techletter.core.logging import setup_logging  # noqa: PLC0415
        from techletter.settings import get_settings  # noqa: PLC0415

        settings = get_settings()
        setup_logging(settings.log_level, settings.service_name)
        container = await Container.open(settings, create_indexes=create_indexes)
        try:
            await body(container)
        finally:
            await container.close()

    asyncio.run(run())


def _run_worker(build: Callable[[Container], Coroutine[Any, Any, None]], *, service: str) -> None:
    """워커 프로세스: 컨테이너 → 러너 → SIGTERM drain."""

    async def run() -> None:
        from techletter.container import Container  # noqa: PLC0415
        from techletter.core.logging import get_logger, setup_logging  # noqa: PLC0415
        from techletter.settings import get_settings  # noqa: PLC0415

        settings = get_settings()
        setup_logging(settings.log_level, service)
        logger = get_logger(service)
        container = await Container.open(settings)
        logger.info("worker starting", extra={"version": __version__})
        try:
            await build(container)
        finally:
            await container.close()
            logger.info("worker stopped")

    asyncio.run(run())


@app.command()
def version() -> None:
    """버전을 출력한다."""
    typer.echo(__version__)


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", help="바인드 주소"),
    port: int = typer.Option(8080, help="포트"),
    reload: bool = typer.Option(False, "--reload", help="코드 변경 시 재시작(개발용)"),
) -> None:
    """FastAPI 서버를 기동한다."""
    # CLI 기동 속도를 위해 무거운 의존성은 해당 커맨드에서만 올린다.
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "techletter.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        access_log=False,
        log_config=None,
    )


@app.command()
def worker() -> None:
    """RSS 스케줄러 + 잡 컨슈머 + 유지보수."""

    async def build(container: Container) -> None:
        from techletter.workers.core_worker import build_core_worker  # noqa: PLC0415
        from techletter.workers.runtime import run_with_shutdown  # noqa: PLC0415

        core = build_core_worker(container)
        await run_with_shutdown(core.run_forever, on_signal=core.request_stop)

    _run_worker(build, service="techletter-worker")


@app.command(name="summary-worker")
def summary_worker() -> None:
    """요약 잡 워커(Playwright 포함)."""

    async def build(container: Container) -> None:
        from techletter.workers.runtime import run_with_shutdown  # noqa: PLC0415
        from techletter.workers.summary_worker import build_summary_worker  # noqa: PLC0415

        runner, renderer = build_summary_worker(container)
        try:
            await run_with_shutdown(runner.run_forever, on_signal=runner.request_stop)
        finally:
            # 브라우저를 반드시 닫는다. 남으면 컨테이너가 메모리를 쥔 채 좀비가 된다.
            await renderer.aclose()

    _run_worker(build, service="techletter-summary-worker")


@app.command(name="embedding-worker")
def embedding_worker() -> None:
    """임베딩 잡 워커."""

    async def build(container: Container) -> None:
        from techletter.workers.embedding_worker import build_embedding_worker  # noqa: PLC0415
        from techletter.workers.runtime import run_with_shutdown  # noqa: PLC0415

        runner = build_embedding_worker(container)
        await run_with_shutdown(runner.run_forever, on_signal=runner.request_stop)

    _run_worker(build, service="techletter-embedding-worker")


@app.command(name="all")
def run_all() -> None:
    """api + worker를 한 프로세스에서 실행한다(로컬 개발 전용).

    운영에서는 쓰지 않는다 — 워커가 API 응답 지연에 영향을 준다.
    """

    async def build(container: Container) -> None:
        import uvicorn  # noqa: PLC0415

        from techletter.app import create_app  # noqa: PLC0415
        from techletter.workers.core_worker import build_core_worker  # noqa: PLC0415

        core = build_core_worker(container)
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(container.settings),
                host="0.0.0.0",
                port=container.settings.api_port,
                access_log=False,
                log_config=None,
            )
        )
        await asyncio.gather(server.serve(), core.run_forever())

    _run_worker(build, service="techletter-all")


@app.command(name="ensure-indexes")
def ensure_indexes() -> None:
    """MongoDB 인덱스를 생성한다."""

    async def body(container: Container) -> None:
        from techletter.core.db.indexes import ensure_indexes as apply  # noqa: PLC0415

        created = await apply(container.db)
        for collection, names in sorted(created.items()):
            typer.echo(f"{collection}: {', '.join(names)}")

    _with_container(body)


@jobs_app.command("list")
def jobs_list(
    status: str = typer.Option("dead", help="pending|running|done|dead"),
    job_type: str = typer.Option("", "--type", help="잡 타입으로 필터"),
    limit: int = typer.Option(20),
) -> None:
    """잡을 조회한다."""

    async def body(container: Container) -> None:
        from techletter.core.pagination import Page  # noqa: PLC0415

        jobs, total = await container.queue.list_jobs(
            Page(1, limit), status=status or None, job_type=job_type or None
        )
        typer.echo(f"{total}건 중 {len(jobs)}건")
        for job in jobs:
            error = (job.last_error or "")[:80]
            typer.echo(
                f"{job.id}  {job.type.value:<28} {job.status.value:<8} "
                f"attempt={job.attempt}/{job.max_attempt}  key={job.key}  {error}"
            )

    _with_container(body)


@jobs_app.command("stats")
def jobs_stats() -> None:
    """상태·타입별 집계를 본다."""

    async def body(container: Container) -> None:
        stats = await container.queue.stats()
        for key, value in sorted(stats["by_status"].items()):
            typer.echo(f"{key:<10} {value}")
        if stats["by_type"]:
            typer.echo("---")
            for key, value in sorted(stats["by_type"].items()):
                typer.echo(f"{key:<40} {value}")

    _with_container(body)


@jobs_app.command("retry")
def jobs_retry(
    job_id: str = typer.Argument("", help="비우면 --type/--kind 조건으로 일괄 재시도"),
    job_type: str = typer.Option("", "--type"),
    error_kind: str = typer.Option("", "--kind", help="retryable|permanent|quota"),
    limit: int = typer.Option(100),
) -> None:
    """dead 잡을 다시 큐에 넣는다."""

    async def body(container: Container) -> None:
        from techletter.core.ids import to_object_id  # noqa: PLC0415

        if job_id:
            oid = to_object_id(job_id)
            job = await container.queue.retry(oid) if oid else None
            typer.echo("재시도함" if job else "대상 없음 (dead 잡이 아니거나 없다)")
            return
        retried = await container.queue.retry_bulk(
            job_type=job_type or None, error_kind=error_kind or None, limit=limit
        )
        typer.echo(f"{retried}건 재시도")

    _with_container(body)


@jobs_app.command("purge")
def jobs_purge(older_than_days: int = typer.Option(30)) -> None:
    """오래된 완료/dead 잡을 삭제한다.

    `done`은 TTL 인덱스가 14일 뒤 자동으로 지운다. 이 명령은 `dead`를 손으로
    치울 때 쓴다.
    """

    async def body(container: Container) -> None:
        from datetime import timedelta  # noqa: PLC0415

        from techletter.core.jobs.types import COLLECTION, JobStatus  # noqa: PLC0415
        from techletter.core.time import utcnow  # noqa: PLC0415

        cutoff = utcnow() - timedelta(days=older_than_days)
        result = await container.db[COLLECTION].delete_many(
            {
                "status": {"$in": [JobStatus.DONE.value, JobStatus.DEAD.value]},
                "updated_at": {"$lt": cutoff},
            }
        )
        typer.echo(f"{result.deleted_count}건 삭제")

    _with_container(body)


@backfill_app.command("summaries")
def backfill_summaries(
    limit: int = typer.Option(50),
    priority: int = typer.Option(
        10, help="숫자가 클수록 나중에 처리된다. 신규 수집물보다 뒤로 미룬다."
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """요약이 없는 포스트에 대해 잡을 넣는다. 본문이 있으면 요약만, 없으면 가져오기부터."""

    async def body(container: Container) -> None:
        from techletter.content.service import request_summary  # noqa: PLC0415

        posts = await container.posts.find_unsummarized(limit)
        if dry_run:
            typer.echo(f"[dry-run] {len(posts)}건이 대상이다. --execute 로 실행한다.")
            for post in posts[:10]:
                typer.echo(f"  {post.id}  {post.title[:60]}")
            return
        queued = [
            (await request_summary(container.queue, container.posts, post, priority=priority))[1]
            for post in posts
        ]
        enqueued = sum(job is not None for job in queued)
        typer.echo(f"{enqueued}건 enqueue (중복 {len(posts) - enqueued}건 건너뜀)")

    _with_container(body)


@backfill_app.command("topics")
def backfill_topics(
    limit: int = typer.Option(0, help="0이면 대상 전부"),
    batch_size: int = typer.Option(20, min=1, max=40),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """주제 목록 밖의 카테고리를 가진 글을 다시 분류한다.

    제목·요약·키워드만 보내 여러 건을 한 번에 분류한다. 중간에 멈춰도 다시
    돌리면 남은 글부터 이어진다. dry-run은 첫 묶음을 분류해 보여 주기만 한다.
    """

    async def body(container: Container) -> None:
        from techletter.summary.topics import TOPIC_NAMES  # noqa: PLC0415
        from techletter.workers.summary_worker import build_summarizer  # noqa: PLC0415

        summarizer = build_summarizer(container)
        done = failed_batches = 0
        while True:
            want = batch_size if limit <= 0 else min(batch_size, limit - done)
            if want <= 0:
                break
            posts = await container.posts.find_needing_topics(TOPIC_NAMES, want)
            if not posts:
                break
            try:
                results = await summarizer.classify_topics([_topic_input(p) for p in posts])
            except Exception as exc:
                typer.echo(f"분류 실패: {type(exc).__name__}: {str(exc)[:200]}")
                failed_batches += 1
                if failed_batches >= 3:
                    typer.echo("연속 실패 3회 — 멈춘다. 나중에 다시 돌리면 이어진다.")
                    break
                continue
            failed_batches = 0
            if dry_run:
                for post in posts:
                    topics = ", ".join(results.get(str(post.id), ["(누락)"]))
                    typer.echo(f"  {post.title[:50]}  →  {topics}")
                typer.echo("[dry-run] 첫 묶음만 분류했다. --execute 로 실행한다.")
                return
            for post in posts:
                topics = results.get(str(post.id))
                if topics and await container.posts.set_categories(str(post.id), topics):
                    done += 1
            if not results:
                failed_batches += 1
            typer.echo(f"{done}건 분류")
        remaining = len(await container.posts.find_needing_topics(TOPIC_NAMES, 10_000))
        typer.echo(f"완료: {done}건 분류, 남은 대상 {remaining}건")

    _with_container(body)


def _topic_input(post: Post) -> dict[str, Any]:
    summary = post.aisummary
    return {
        "id": str(post.id),
        "title": post.title,
        "blog": post.blog_name,
        "summary": (summary.summary if summary else "") or "",
        "keywords": (summary.tags if summary else [])[:7],
    }


@backfill_app.command("embeddings")
def backfill_embeddings(
    limit: int = typer.Option(50),
    priority: int = typer.Option(
        10, help="숫자가 클수록 나중에 처리된다. 신규 수집물보다 뒤로 미룬다."
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """요약됐지만 임베딩되지 않은 포스트를 채운다."""

    async def body(container: Container) -> None:
        from techletter.content.jobs import enqueue_embedding_requested  # noqa: PLC0415

        posts = await container.posts.find_summarized_not_embedded(limit)
        if dry_run:
            typer.echo(f"[dry-run] {len(posts)}건이 대상이다. --execute 로 실행한다.")
            return
        queued = [
            await enqueue_embedding_requested(container.queue, str(post.id), priority=priority)
            for post in posts
        ]
        typer.echo(f"{sum(job is not None for job in queued)}건 enqueue")

    _with_container(body)


@backfill_app.command("icons")
def backfill_icons(
    all_blogs: bool = typer.Option(False, "--all", help="이미 받아 둔 블로그도 다시 받는다."),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """블로그 아이콘 수집 잡을 건다. 기본은 아직 한 번도 시도하지 않은 블로그만."""

    async def body(container: Container) -> None:
        from techletter.content.icons import BlogIconRepository, enqueue_icon_fetch  # noqa: PLC0415
        from techletter.core.pagination import Page  # noqa: PLC0415

        blogs, _ = await container.blogs.list_blogs(Page(1, 1000), active=None)
        tried = (
            set() if all_blogs else await BlogIconRepository(container.db).blog_ids_with_record()
        )
        targets = [b for b in blogs if b.id is not None and str(b.id) not in tried]
        if dry_run:
            typer.echo(f"[dry-run] {len(targets)}개 블로그가 대상이다. --execute 로 실행한다.")
            return
        queued = [await enqueue_icon_fetch(container.queue, str(b.id)) for b in targets]
        typer.echo(f"{sum(job is not None for job in queued)}건 enqueue")

    _with_container(body)


async def _collect_missing_link_key_posts(container: Container, batch_size: int) -> list[Post]:
    posts: list[Post] = []
    after_id = None
    while True:
        batch = await container.posts.find_missing_link_keys(batch_size, after_id=after_id)
        if not batch:
            break
        posts.extend(batch)
        after_id = batch[-1].id
        if after_id is None or len(batch) < batch_size:
            break
    return posts


def _link_key_collisions(
    candidates: list[tuple[Post, str]], existing: list[Post]
) -> tuple[set[str], list[tuple[str, str, str]]]:
    by_key: dict[str, list[Post]] = {}
    for post, link_key in candidates:
        by_key.setdefault(link_key, []).append(post)
    for post in existing:
        if isinstance(post.link_key, str):
            by_key.setdefault(post.link_key, []).append(post)

    collision_pairs: list[tuple[str, str, str]] = []
    collision_keys: set[str] = set()
    for link_key, matching in by_key.items():
        by_id = {str(post.id): post for post in matching if post.id is not None}
        if len(by_id) < 2:
            continue
        collision_keys.add(link_key)
        ids = sorted(by_id)
        collision_pairs.extend((link_key, first, second) for first, second in combinations(ids, 2))
    collision_pairs.sort()
    return collision_keys, collision_pairs


@backfill_app.command("link-keys")
def backfill_link_keys(
    batch_size: int = typer.Option(500, "--batch-size", min=1),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """link_key가 없는 포스트를 채운다. 충돌 문서는 사람이 판단할 때까지 보류한다."""

    async def body(container: Container) -> None:
        posts = await _collect_missing_link_key_posts(container, batch_size)

        candidates: list[tuple[Post, str]] = []
        for post in posts:
            link_key = normalize_link(post.link)
            candidates.append((post, link_key))

        existing = await container.posts.find_by_link_keys([link_key for _, link_key in candidates])
        collision_keys, collision_pairs = _link_key_collisions(candidates, existing)

        mode = "[dry-run]" if dry_run else "[execute]"
        typer.echo(f"{mode} link_key 없는 {len(candidates)}건이 대상이다.")
        typer.echo(f"충돌 {len(collision_pairs)}쌍")
        if collision_pairs:
            typer.echo("충돌 쌍 목록:")
            for link_key, first, second in collision_pairs:
                typer.echo(f"  link_key={link_key}  {first} <-> {second}")
        if dry_run:
            typer.echo("--execute 로 실행한다.")
            return

        updated = 0
        for post, link_key in candidates:
            if link_key in collision_keys or post.id is None:
                continue
            if await container.posts.update_link_key(str(post.id), link_key):
                updated += 1
        typer.echo(f"{updated}건 갱신, 충돌 {len(collision_pairs)}쌍은 건너뛰었다.")

    _with_container(body)


@settings_app.command("check")
def settings_check() -> None:
    """필수 환경변수가 모두 있는지 검증한다(값은 출력하지 않는다)."""
    from pydantic import ValidationError  # noqa: PLC0415

    from techletter.settings import Settings  # noqa: PLC0415

    try:
        loaded = Settings.load()
    except ValidationError as exc:
        typer.secho("설정 검증 실패:", fg=typer.colors.RED, err=True)
        for err in exc.errors():
            typer.echo(f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}", err=True)
        raise typer.Exit(1) from exc
    typer.secho(f"설정 OK (service={loaded.service_name}, db={loaded.mongo.db_name})", fg="green")


# Settings 자체의 필드 중 서브모델(예: mongo, router)은 env var가 아니라 조립
# 대상이라 출력에서 뺀다. 이름은 settings.py의 Settings.load() 인자와 동기화한다.
_NESTED_SETTINGS_FIELDS = frozenset(
    {
        "mongo",
        "qdrant",
        "router",
        "jobs",
        "rss",
        "summary",
        "embedding",
        "chat",
        "auth_settings",
        "summary_llm",
        "embedding_llm",
        "chat_llm",
    }
)


def _field_default(field: Any) -> str:
    if field.is_required():
        return ""
    value = field.default_factory() if field.default_factory is not None else field.default
    if value in (None, [], ""):
        return ""
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


@settings_app.command("example")
def settings_example() -> None:
    """`.env.example` 형식으로 전체 환경변수 목록을 출력한다(시크릿 값은 채우지 않는다)."""
    from techletter.settings import (  # noqa: PLC0415
        AuthSettings,
        ChatLlmSettings,
        ChatSettings,
        EmbeddingLlmSettings,
        EmbeddingSettings,
        JobSettings,
        MongoSettings,
        QdrantSettings,
        RouterSettings,
        RssSettings,
        Settings,
        SummaryLlmSettings,
        SummarySettings,
    )

    sections: list[tuple[str, type[Any]]] = [
        ("서비스", Settings),
        ("MongoDB", MongoSettings),
        ("Qdrant", QdrantSettings),
        ("인증 (Google OAuth · JWT)", AuthSettings),
        ("요약 워커 LLM", SummaryLlmSettings),
        ("임베딩 LLM (워커·챗봇 공용)", EmbeddingLlmSettings),
        ("챗봇 LLM", ChatLlmSettings),
        ("LLM 모델 라우터", RouterSettings),
        ("잡 큐", JobSettings),
        ("RSS 수집", RssSettings),
        ("요약 파이프라인", SummarySettings),
        ("임베딩 파이프라인", EmbeddingSettings),
        ("챗봇", ChatSettings),
    ]
    lines: list[str] = []
    for title, cls in sections:
        prefix = cls.model_config.get("env_prefix", "") or ""
        lines.append(f"# {title}")
        for name, field in cls.model_fields.items():
            if name in _NESTED_SETTINGS_FIELDS:
                continue
            # env_prefix만 있는 필드(예: LLM 서브클래스)는 alias가 없다 —
            # pydantic-settings가 prefix + 필드명으로 env var를 만든다.
            env_name = (field.alias or f"{prefix}{name}").upper()
            lines.append(f"{env_name}={_field_default(field)}")
        lines.append("")
    typer.echo("\n".join(lines).rstrip() + "\n", nl=False)


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
