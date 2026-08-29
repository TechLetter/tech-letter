"""`techletter` 단일 진입점.

프로세스 4종이 전부 여기서 나온다(01 §1).
    techletter api               HTTP 서버
    techletter worker            RSS 스케줄러 · 잡 컨슈머 · 재시도
    techletter summary-worker    요약 파이프라인 (Playwright)
    techletter embedding-worker  임베딩 파이프라인
    techletter all               api + worker (로컬 개발용)
"""

from __future__ import annotations

import typer

from techletter import __version__

app = typer.Typer(
    name="techletter",
    help="Tech-Letter 서비스 실행·운영 도구",
    no_args_is_help=True,
    add_completion=False,
)
jobs_app = typer.Typer(help="잡 큐 조회·재처리 (ADR-0004)", no_args_is_help=True)
backfill_app = typer.Typer(help="누락분 백필", no_args_is_help=True)
settings_app = typer.Typer(help="설정 점검", no_args_is_help=True)
app.add_typer(jobs_app, name="jobs")
app.add_typer(backfill_app, name="backfill")
app.add_typer(settings_app, name="settings")

_NOT_YET = "아직 구현되지 않았다 (계획: docs/plan/06-migration-steps.md)"


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
    """RSS 스케줄러 + 잡 컨슈머 + 재시도 스케줄러."""
    raise typer.Exit(_fail("worker"))


@app.command(name="summary-worker")
def summary_worker() -> None:
    """요약 잡 워커(Playwright 포함)."""
    raise typer.Exit(_fail("summary-worker"))


@app.command(name="embedding-worker")
def embedding_worker() -> None:
    """임베딩 잡 워커."""
    raise typer.Exit(_fail("embedding-worker"))


@app.command(name="all")
def run_all(reload: bool = typer.Option(False, "--reload")) -> None:
    """api + worker를 한 프로세스에서 실행한다(로컬 개발 전용)."""
    raise typer.Exit(_fail("all"))


@app.command(name="ensure-indexes")
def ensure_indexes() -> None:
    """MongoDB 인덱스를 생성한다(05 §1.3~1.4)."""
    raise typer.Exit(_fail("ensure-indexes"))


@jobs_app.command("list")
def jobs_list(
    status: str = typer.Option("dead", help="pending|running|done|failed|dead"),
    limit: int = typer.Option(20),
) -> None:
    """잡을 조회한다."""
    raise typer.Exit(_fail("jobs list"))


@jobs_app.command("retry")
def jobs_retry(job_id: str) -> None:
    """실패한 잡을 다시 큐에 넣는다."""
    raise typer.Exit(_fail("jobs retry"))


@jobs_app.command("purge")
def jobs_purge(older_than_days: int = typer.Option(30)) -> None:
    """오래된 완료/실패 잡을 삭제한다."""
    raise typer.Exit(_fail("jobs purge"))


@backfill_app.command("summaries")
def backfill_summaries(
    limit: int = typer.Option(50),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """요약이 없는 포스트에 대해 요약 잡을 넣는다."""
    raise typer.Exit(_fail("backfill summaries"))


@backfill_app.command("embeddings")
def backfill_embeddings(
    limit: int = typer.Option(50),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
) -> None:
    """요약됐지만 임베딩되지 않은 포스트를 채운다."""
    raise typer.Exit(_fail("backfill embeddings"))


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


@settings_app.command("example")
def settings_example() -> None:
    """`.env.example` 내용을 표준출력으로 생성한다."""
    raise typer.Exit(_fail("settings example"))


def _fail(name: str) -> int:
    typer.secho(f"`{name}`: {_NOT_YET}", fg=typer.colors.YELLOW, err=True)
    return 2


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
