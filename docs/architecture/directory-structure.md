# 디렉토리 구조 · 코드 규약

## 1. 트리

```
tech-letter/
├── pyproject.toml                # [project] techletter. dependency-groups. ruff/pyright/pytest 설정
├── uv.lock  .python-version(3.12)  .pre-commit-config.yaml  scripts/dev.sh
├── .gitignore  .dockerignore  README.md
│
├── src/techletter/
│   ├── __main__.py  cli.py       # typer: api | worker | summary-worker | embedding-worker | all
│   │                             #        | jobs {list,retry,purge} | backfill {summaries,embeddings}
│   │                             #        | ensure-indexes | settings {check,example}
│   ├── settings.py               # pydantic-settings 단일 트리
│   ├── app.py                    # create_app(): lifespan, 미들웨어, 라우터, 예외 핸들러
│   ├── container.py              # Container: mongo/qdrant/http 클라이언트 라이프사이클, 레포지토리·서비스 조립
│   │
│   ├── core/
│   │   ├── errors.py             # AppError(code,status) 서브클래스들 · RetryableError · PermanentError · QuotaExceededError
│   │   ├── logging.py            # JSON 로거
│   │   ├── time.py  ids.py  pagination.py     # utcnow / ObjectId 변환 / 관용 파서 + Page
│   │   ├── http.py               # 공유 httpx.AsyncClient
│   │   ├── db/
│   │   │   ├── mongo.py          # AsyncMongoClient 라이프사이클
│   │   │   ├── documents.py      # BaseDocument(_id alias), SubDocument
│   │   │   ├── indexes.py        # IndexRegistry — 부팅 시 인덱스 생성
│   │   │   └── qdrant.py         # AsyncQdrantClient 라이프사이클
│   │   ├── jobs/
│   │   │   ├── types.py          # JobType, JobStatus, ErrorKind
│   │   │   ├── models.py         # Job 문서 모델
│   │   │   ├── queue.py          # enqueue/claim/complete/fail/retry/stats/count_dead
│   │   │   ├── policy.py         # RetryPolicy(backoff·쿼터 대기·max_attempt), dead_retryable_alert
│   │   │   └── runner.py         # JobRunner: claim 루프 → 핸들러 → 상태 전이
│   │   ├── llm/
│   │   │   ├── chat.py           # LangChainChatClient, RoutingChatClient, LlmGateway
│   │   │   ├── embeddings.py     # LangChainEmbedder
│   │   │   ├── router.py         # 모델 라우터: 큐레이션 ∩ 헬스, 순차 폴백
│   │   │   ├── scouter.py        # 최근 헬스 기록 집계 + TTL 캐시 + 정적 폴백
│   │   │   ├── model_scan.py     # OpenRouter :free 모델 헬스체크(주기 스캔) + 저장
│   │   │   ├── stats.py          # llm_model_stats 기록/조회, 자동 강등 판정
│   │   │   ├── budget.py         # llm_daily_usage, 쿼터 리셋 계산
│   │   │   └── errors.py         # provider 예외 → Quota/Retryable/Permanent 분류
│   │   └── security/  tokens.py  bearer.py     # JWT 발급/검증, Authorization 헤더 추출
│   │
│   ├── api/
│   │   ├── deps.py               # optional_user / current_user / admin_user, 서비스 제공자
│   │   ├── middleware.py         # RequestTrace(순수 ASGI — SSE 안전)
│   │   ├── errors.py             # 예외 → {"error":{code,message,details}} 변환, 422→400
│   │   ├── schemas/               # 외부 계약 DTO
│   │   │   ├── common.py         # Paged[T]/Listing[T], ErrorBody
│   │   │   ├── content.py user.py chat.py admin.py query.py
│   │   └── v1/
│   │       ├── router.py         # /api/v1 조립
│   │       ├── health.py  metrics.py  auth.py  me.py  posts.py  bookmarks.py  blogs.py  filters.py  trends.py
│   │       ├── chat.py           # /chat/messages, /chat/messages/stream(SSE), /chat/sessions*, suggested-questions
│   │       └── admin/  posts.py blogs.py users.py suggested_questions.py jobs.py llm_models.py backfill.py
│   │
│   ├── content/                  # posts·blogs·RSS·필터·트렌드
│   │   ├── models.py repositories.py service.py filters.py trends.py
│   │   ├── rss/  feeder.py  aggregator.py
│   │   ├── jobs.py               # payload 스키마 + enqueue 헬퍼
│   │   └── handlers.py           # on_summary_completed 등
│   ├── users/
│   │   ├── models.py repositories.py service.py credits.py auth_service.py
│   ├── chat/
│   │   ├── models.py repositories.py sessions.py suggested_questions.py
│   │   ├── use_case.py           # ChatUseCase: 가드→세션→차감→에이전트→기록/환불
│   │   ├── guards/  prompt.py output.py retrieved.py rules.py models.py
│   │   ├── memory.py handlers.py
│   │   └── agent/  state.py graph.py planner.py answer.py prompts.py policies.py
│   │               tools/  content_posts.py  vector_search.py
│   ├── summary/                  # summary-worker 전용 의존(playwright, trafilatura, bs4, Pillow)
│   │   ├── renderer.py parser.py validator.py summarizer.py constants.py pipeline.py handlers.py
│   ├── embedding/
│   │   ├── chunker.py pipeline.py handlers.py
│   └── workers/
│       ├── runtime.py            # heartbeat 파일, graceful shutdown(SIGTERM→drain)
│       ├── scheduler.py          # 주기 작업(RSS 30분, 유지보수 1분)
│       └── core_worker.py  summary_worker.py  embedding_worker.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/  api/ chat/ content/ core/ embedding/ jobs/ llm/ summary/ users/
│   ├── contract/  snapshots/{current,v2}/     # API 계약 골든 스냅샷
│   ├── integration/              # Mongo·Qdrant 컨테이너, 잡 큐, 파이프라인 e2e
│   ├── e2e/                      # Playwright(프론트+백엔드)
│   └── fixtures/  rss/ html/ seed/
│
├── docker/  Dockerfile  compose.dev.yml  compose.prod.yml
├── scripts/  check_routes.py  contract_diff.py  contract_snapshot.py  eval_models.py  dev.sh  verify_prod_smoke.sh
├── .github/workflows/  ci.yml  deploy.yml
└── docs/  README.md  architecture/  PRIVACY_POLICY.md
```

## 2. `pyproject.toml` 골격

```toml
[project]
name = "techletter"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.122", "uvicorn[standard]>=0.38", "pydantic>=2.12", "pydantic-settings>=2.12",
  "pymongo>=4.15",                  # pymongo.asynchronous
  "qdrant-client>=1.16",
  "httpx>=0.28", "pyjwt>=2.10", "typer>=0.15",
  "langchain-core>=1.4", "langgraph>=1.1",
  "langchain-google-genai>=3.2", "langchain-openai>=1.1", "langchain-text-splitters",
  "feedparser>=6",
]

[project.optional-dependencies]
browser = ["playwright==1.49.1", "trafilatura", "beautifulsoup4", "pillow"]   # summary-worker 이미지에서만

[dependency-groups]
dev = ["pytest", "pytest-asyncio", "pytest-cov", "syrupy", "ruff", "pyright", "pre-commit",
       "playwright==1.49.1", "trafilatura", "beautifulsoup4", "pillow"]

[project.scripts]
techletter = "techletter.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E","F","I","UP","B","ASYNC","DTZ","T20","SIM","RUF","PL","TID","N","ANN"]
ignore = ["ANN401","PLR0913","PLR2004","RUF001","RUF002","RUF003"]
[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.pyright]
include = ["src","tests"]
typeCheckingMode = "standard"
pythonVersion = "3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["integration: 컨테이너(Mongo/Qdrant)가 필요한 테스트",
           "e2e: 실행 중인 스택과 브라우저가 필요한 테스트",
           "contract: 골든 스냅샷 비교",
           "network: 실제 외부 서비스를 호출"]
addopts = "-m 'not integration and not e2e and not network' --strict-markers"
```

## 3. 설정 (`settings.py`)

`Settings`는 중첩된 pydantic-settings 트리다. 주요 서브트리:

```python
class Settings(BaseSettings):
    mongo:      MongoSettings         # MONGO_URI, MONGO_DB_NAME=techletter
    qdrant:     QdrantSettings        # QDRANT_HOST/PORT, QDRANT_COLLECTION_NAME=tech_letter_posts
    router:     RouterSettings        # SCOUTER_SCAN_INTERVAL_HOURS=1, *_MODEL_PREFERENCE, LLM_STATIC_FALLBACK_MODELS,
                                      # LLM_MIN_SUCCESS_RATE, LLM_QUOTA_RESET_UTC_HOUR=7,
                                      # MAX_MODEL_ATTEMPTS=3, SUMMARY_DAILY_BUDGET=20, CHAT_GEMINI_FALLBACK=true
    jobs:       JobSettings           # JOB_POLL_INTERVAL_SECONDS=2, JOB_LOCK_TIMEOUT_MINUTES=30,
                                      # JOB_BACKOFF_MINUTES=[5,30,120,480,1440], JOB_MAX_ATTEMPT=5,
                                      # JOB_DEAD_RETRYABLE_ALERT_THRESHOLD=5
    rss:        RssSettings           # interval=30m, CONTENT_BLOG_FETCH_BATCH_SIZE=10, tls 예외 목록
    summary:    SummarySettings       # RENDERER_STRATEGY, SCRAPERAPI_KEY, SUMMARY_MAX_INPUT_CHARS
    embedding:  EmbeddingSettings     # EMBEDDING_WORKER_CHUNK_SIZE/OVERLAP
    chat:       ChatSettings          # CHATBOT_RAG_TOP_K/_SCORE_THRESHOLD, CHAT_CONTEXT_COMPRESSION_*

    # 지연 로딩 — 워커는 OAuth 자격증명 없이도 부팅한다
    auth:       AuthSettings          # (property) JWT_SECRET, GOOGLE_OAUTH_*, AUTH_LOGIN_SUCCESS_REDIRECT_URL

    summary_llm:    SummaryLlmSettings     # env prefix SUMMARY_WORKER_LLM_   (Gemini, 1순위)
    embedding_llm:  EmbeddingLlmSettings   # env prefix EMBEDDING_WORKER_LLM_ (Gemini 고정)
    chat_llm:       ChatLlmSettings        # env prefix CHATBOT_LLM_          (OpenRouter)
    chat_embedding: ChatEmbeddingSettings  # env prefix CHATBOT_EMBEDDING_

    cors_allowed_origins: list[str]   # CORS_ALLOWED_ORIGINS
    log_level: str = "INFO"
    service_name: str                 # 프로세스별 자동 주입
```
- 시크릿은 `SecretStr`. 필수값이 없으면 부팅 즉시 실패한다.
- `techletter settings example`이 전체 env var 목록을 `.env.example` 형식으로 생성한다(필수값은 빈칸, 나머지는 기본값).
- `techletter settings check`는 배포 전 필수 env 존재만 검증한다(값은 출력하지 않는다).

## 4. 코드 규약

| 항목 | 규약 |
|---|---|
| import | 절대 임포트만(`from techletter.content.service import PostService`). 상대 임포트 금지(ruff) |
| 시간 | `core.time.utcnow()`만. naive datetime 금지(ruff `DTZ`) |
| 예외 | 도메인은 `AppError` 서브클래스만 raise. HTTP 상태·에러코드는 예외 클래스 속성. `HTTPException`은 api 레이어만 |
| 로깅 | `get_logger(__name__)`. 요청 본문·토큰·API 키는 로깅하지 않는다 |
| DI | FastAPI `Depends`는 `api/deps.py`에만. 도메인 서비스는 생성자 주입 → 테스트에서 Fake 주입 |
| 레포지토리 | 컬렉션 1개 = 클래스 1개. 인덱스는 부팅 시 `IndexRegistry`가 1회 생성 |
| 잡 | payload는 pydantic 모델. 핸들러는 멱등하게 작성한다 |
| async | 라우트·핸들러 전부 `async def`. 블로킹 라이브러리(trafilatura, PIL, feedparser 파싱)는 `asyncio.to_thread` |
| LLM | 반드시 `core.llm.router`/`core.llm.chat`을 경유한다. 직접 `ChatOpenAI(...)` 생성 금지 |
| DTO | `api/schemas`가 외부 계약과 1:1. 도메인 모델을 그대로 노출하지 않는다 |
| 네이밍 | 모듈 snake_case, 클래스 PascalCase |
| 문서 모델 | 최상위 문서는 `BaseDocument`(`_id`/`created_at`/`updated_at`), 중첩 서브 객체는 `SubDocument`(이 필드들을 갖지 않는다) |
