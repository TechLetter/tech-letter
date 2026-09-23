# 테스트 전략

## 1. 피라미드

| 층 | 대상 | 도구 | 마커 |
|---|---|---|---|
| **단위** | 도메인 서비스, 가드, 플래너, 파서, 검증기, 잡 정책, LLM 라우터, JWT, 관용 파서 | pytest + Fake | (기본) |
| **계약** | API 56개 라우트의 응답 구조, SSE 프레임 | pytest + httpx `AsyncClient` | `integration` + `contract` |
| **통합** | 레포지토리↔Mongo, 잡 큐 클레임/재시도, Qdrant, 워커 파이프라인 | 실행 중인 Mongo/Qdrant 컨테이너 필요 | `integration` |
| **E2E** | 프론트+백엔드 실제 브라우저 시나리오 | Playwright(pytest-playwright) | `e2e` |

`tests/contract/` 의 계약 모듈에는 `integration`과 `contract` 마커를 **함께** 붙인다(새 파일도 동일 — 모듈 상단 `pytestmark = [pytest.mark.integration, pytest.mark.contract]`). 계약 테스트도 Mongo가 필요하므로 기본 실행에서 제외되며, `uv run pytest -q`는 단위 테스트만 실행한다.

```bash
uv run pytest -q                                      # 단위 415개
./scripts/dev.sh test-infra                           # Mongo 27018 · Qdrant 6334 기동
uv run pytest -q -m integration                       # 통합 + 계약(컨테이너 필요)
uv run pytest -q -m "integration and contract"        # 계약만(컨테이너 필요)
uv run pytest -q -m e2e                                # E2E(실행 중인 스택 + 브라우저)
```

## 2. 계약 테스트

- syrupy 골든 스냅샷은 사용하지 않는다(import 0건이며 의존성도 제거됐다). 계약 테스트는 실제로 `assert set(body) == {...}` 형태의 키 집합과 DTO 네이밍 변환을 고정한다.
- SSE는 프론트 파서와 동일한 규칙으로 파싱해 이벤트 시퀀스와 `done` 키 집합을 검증한다.

## 3. 단위 테스트 — 핵심 커버리지

- `core/pagination`: 관용 파싱 표(`""`, `abc`, `0`, `-1`, `101`).
- `core/jobs/policy`: 백오프 표, 쿼터 리셋 계산(리셋 시각 경계·jitter), attempt 롤백, max 초과 시 dead 전이, `dead_retryable_alert` 임계치.
- `core/jobs/queue`: 중복 억제, 동시 클레임 시 단일 승자, 스테일 락 회수, `count_dead`.
- `core/llm/router`: 요약 체인∩헬스 순서, 챗봇·플래너 자동 후보, 헬스 기록 없을 시 정적 폴백, 429 시 다음 모델, JSON 실패 시 다음 모델, 전부 실패 시 예외 종류.
- `core/llm/chat`: `RoutingChatClient`가 `model_id`로 올바른 provider 클라이언트를 고르는지.
- `chat/use_case`: 순서 보장(가드 실패 시 크레딧 미차감, 차감 실패 시 에이전트 미호출, 에이전트 실패 시 환불 호출).
- `summary/pipeline`: 예외 분류(렌더 실패/봇 차단/파싱 실패 → 각각 다른 처리).
- `api/schemas`: `is_bookmarked` boolean 고정, `ai_summary` null 직렬화, `Paged[T]`의 `total_pages` 계산.

## 4. 통합 테스트

- `test_indexes.py`: `ensure_indexes()` 후 실제 인덱스가 [data-model.md](data-model.md)와 일치(이름·키·옵션·TTL).
- `test_job_queue.py`: 병렬 클레임, 재시도 전이 4종, 스테일 락 회수, `count_dead`, TTL 인덱스.
- `tests/integration/test_credits.py::test_concurrent_consume_never_goes_negative`: 동시 consume → 잔액이 절대 음수가 되지 않음.
- `test_pipeline_e2e.py`: RSS 픽스처 → summary(Fake) → embedding(Fake) → Qdrant → `GET /posts`.
- `test_content_aggregator.py`: 연속 실패 시 블로그 자동 비활성화.

## 4.1 커버리지 공백

- `workers/**`, `cli.py`, `api/**`는 직접 테스트가 0건이며, API는 계약 테스트가 간접적으로 커버한다.
- `PlaywrightRenderer` 테스트는 0건이다. 렌더러 테스트는 차단 페이지 판정(`needs_retry`)만 다룬다.

## 5. E2E 시나리오

로컬 스택: `./scripts/dev.sh test-infra`로 테스트용 Mongo(27018)·Qdrant(6334)를 띄운 뒤 `techletter all`과 API를 실행한다. E2E는 `E2E_UI_DIST=../tech-letter_ui/dist`에 정적 빌드를 준비하면 fixture가 4173 포트에서 자체 서빙한다. `npm run dev`로는 이 절차가 성립하지 않는다.

주의: `docker compose -f docker/compose.dev.yml up -d mongo qdrant`는 기본 개발 포트(27017/6333)만 열어 통합 테스트에 붙지 않는다. 통합·계약 테스트에는 반드시 `./scripts/dev.sh test-infra`를 사용한다.

기본값은 `E2E_MONGO_URI=mongodb://localhost:27018`, `E2E_API_URL=http://localhost:8080`이다. 프론트에서 `npm ci && npm run build`를 먼저 실행한 뒤 `E2E_UI_DIST=../tech-letter_ui/dist E2E_MONGO_URI=mongodb://localhost:27018 E2E_API_URL=http://localhost:8080 uv run pytest -q tests/e2e -m e2e`를 실행한다. 시나리오는 13종이다.

| 시나리오 | 검증 |
|---|---|
| 홈 포스트 목록·필터 | 카드가 보이고 콘솔 오류가 없음 |
| 홈 무한스크롤 | `total_pages` 기반으로 다음 페이지를 요청 |
| 홈 v2 요청 계약 | `/posts` 요청에 폐기된 파라미터가 없고 필터 요청이 존재 |
| 로그인 → 북마크 토글 → 북마크 페이지 | POST 201, 북마크 목록 반영 |
| 트렌드 렌더링 | `items` 응답을 사용하고 모든 요청이 200 |
| 챗봇 SSE 답변 | 스트림 경로와 200/402/429/503 응답 처리 |
| 크레딧 0 상태에서 질문 | 스트림 전에 402 `credit.insufficient` |
| 챗 세션 목록 | 세션 목록 요청이 성공 |
| 어드민 포스트 목록 | v2 필드와 요약 모델명이 화면에 표시 |
| 어드민 운영 탭 | 잡 통계 요청과 상태 카드 표시 |
| 어드민 모델 탭 | 요약 폴백 체인 조회 요청이 200이고 `purpose=summary` 1건 |
| 일반 사용자의 어드민 접근 | 어드민 요청이 403이거나 요청하지 않음 |
| 만료 토큰 접근 | 401 인터셉터가 토큰을 삭제 |

각 시나리오는 실패 시 스크린샷·콘솔 로그를 남긴다. 콘솔 에러 0을 기준으로 판정한다.

## 6. CI (`.github/workflows/ci.yml`)

PR과 `develop`/`main` push에서 4개 잡이 병렬로 돈다.

| 잡 | 내용 |
|---|---|
| `check` | `ruff check`/`format --check`(ASYNC/DTZ/TID 포함) → `pyright` → 단위 테스트 |
| `integration` | 실제 mongo:8.0·qdrant:v1.16.2 서비스 컨테이너로 통합·계약 테스트 |
| `e2e` | `tech-letter_ui`를 체크아웃해 빌드하고, 실제 API 프로세스를 띄운 뒤 Playwright로 시나리오 실행(프론트 체크아웃 실패 시 경고만 남기고 건너뜀) |
| `images` | 런타임/브라우저 이미지 빌드 + **크기 게이트**(런타임 ≤450MB, 브라우저 ≤1200MB) + 컨테이너 안에서 `techletter version`과 필수 의존성 import 스모크 |

로컬에서 같은 검사를 하려면:
```bash
./scripts/dev.sh check   # lint → typecheck → test
```

프론트: `npm run lint`, `npm run build`.

## 7. 배포 스모크 (`scripts/verify_prod_smoke.sh`)

배포 파이프라인이 이미지를 교체한 직후 실행한다. `Start` 또는 Smoke가 실패하면 직전 이미지 태그로 자동 롤백한다.

```
1/5 GET /health                          → 200 {"status":"ok"}
2/5 GET /api/v1/posts?page_size=1        → items/page/page_size/total/total_pages 키 존재
3/5 GET /api/v1/me (토큰 없음)             → 401
4/5 GET /api/v1/posts/{잘못된 ObjectId}   → 404, code="resource.not_found"
5/5 worker/summary-worker/embedding-worker 컨테이너 healthcheck   → healthy
```
