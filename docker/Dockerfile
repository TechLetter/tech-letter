# syntax=docker/dockerfile:1
#
# 이미지 두 개를 한 파일에서 만든다.
#   runtime  — api · worker · embedding-worker (브라우저 없음)
#   browser  — summary-worker (Playwright chromium 포함)
#
# 현행은 서비스마다 Dockerfile 이 따로 있었고(7개), summary_worker 는
# 빌드 스테이지의 `/usr/lib` 를 통째로 복사해 이미지가 2.9GB 였다
# (ISSUE-015). 여기서는 chromium 이 실제로 요구하는 라이브러리만 설치한다.

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.10.6

# ── 의존성 ────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS deps
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# 락 파일만 먼저 복사한다. 소스가 바뀌어도 의존성 레이어를 다시 만들지 않는다.
ARG EXTRAS=""
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project ${EXTRAS}

COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev ${EXTRAS}

# ── 공통 런타임 ───────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul \
    PATH="/app/.venv/bin:$PATH"

# curl 은 compose healthcheck 가 쓴다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 techletter

WORKDIR /app
COPY --from=deps --chown=techletter:techletter /app/src /app/src

USER techletter
# tini 가 PID 1 을 맡아 SIGTERM 을 프로세스에 정확히 전달한다.
# 이게 없으면 워커의 graceful drain 이 동작하지 않는다.
ENTRYPOINT ["/usr/bin/tini", "--"]

# ── api · worker · embedding-worker ───────────────────────────────
FROM runtime-base AS runtime
COPY --from=deps --chown=techletter:techletter /app/.venv /app/.venv
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1
CMD ["techletter", "api"]

# ── summary-worker (브라우저 포함) ────────────────────────────────
FROM deps AS deps-browser
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra browser

FROM runtime-base AS browser
USER root
# 본문 추출·이미지 처리 의존까지 포함된 venv 로 갈아 끼운다.
COPY --from=deps-browser --chown=techletter:techletter /app/.venv /app/.venv

# chromium 이 실제로 링크하는 라이브러리만. CJK 폰트는 넣지 않는다 —
# 우리는 페이지를 그리지 않고 DOM 만 읽는다(100MB 절약).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# 브라우저는 앱 유저의 홈에 둔다. root 캐시를 복사하면 실행 시 못 읽는다.
ENV PLAYWRIGHT_BROWSERS_PATH=/home/techletter/.cache/ms-playwright
USER techletter
# `--only-shell` 은 headless shell 만 받는다. 전체 chromium 번들에는
# 우리가 쓰지 않는 headed 바이너리와 ffmpeg 이 들어 있다.
RUN python -m playwright install --only-shell chromium

# 워커에는 HTTP 포트가 없다. 러너가 남기는 heartbeat 파일의 나이를 본다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import pathlib,time,sys; p=pathlib.Path('/tmp/techletter-heartbeat'); sys.exit(0 if p.exists() and time.time()-p.stat().st_mtime < 120 else 1)"
CMD ["techletter", "summary-worker"]
