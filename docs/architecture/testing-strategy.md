# 테스트 전략

## 1. 피라미드

| 층 | 대상 | 도구 | 마커 |
|---|---|---|---|
| **단위** | 도메인 서비스, 가드, 플래너, 파서, 검증기, 잡 정책, LLM 라우터, JWT, 관용 파서 | pytest + Fake | (기본) |
| **계약** | API 49개 라우트의 응답 구조, SSE 프레임 | pytest + httpx `AsyncClient` + syrupy 스냅샷 | `contract` |
| **통합** | 레포지토리↔Mongo, 잡 큐 클레임/재시도, Qdrant, 워커 파이프라인 | 실행 중인 Mongo/Qdrant 컨테이너 필요 | `integration` |
| **E2E** | 프론트+백엔드 실제 브라우저 시나리오 | Playwright(pytest-playwright) | `e2e` |
| 네트워크 | 실제 RSS, 실제 LLM/scouter 호출 | 수동 실행 | `network` |

기본 실행(`uv run pytest`)은 `-m "not integration and not e2e and not network"`.

```bash
uv run pytest -q                                                          # 단위 + 계약
TEST_MONGO_URI=mongodb://localhost:27018 uv run pytest -q -m integration  # 통합(컨테이너 필요)
uv run pytest -q -m e2e                                                    # E2E(실행 중인 스택 + 브라우저)
```

## 2. 계약 테스트

- `tests/contract/snapshots/`에 골든 스냅샷을 둔다(`current/`는 참고용, `v2/`가 실제 회귀 방지선).
- 정규화 규칙: 문자열은 타입 토큰(`"<str>"`), ObjectId는 `"<oid>"`, datetime은 `"<dt>"`, 숫자는 `"<int>"`/`"<float>"`, `null`은 값 그대로 보존, 배열은 첫 원소의 shape + 비어있음 여부만 비교한다. 키 순서는 무관하다.
- `scripts/check_routes.py`가 API 계약 문서(`docs/architecture/api-contract.md`)의 엔드포인트 표와 실제 `app.openapi()` 스키마를 대조해 라우트 커버리지를 검증한다.
- SSE는 프론트 파서와 동일한 규칙으로 파싱해 이벤트 시퀀스와 `done` 키 집합을 검증한다.

## 3. 단위 테스트 — 핵심 커버리지

- `core/pagination`: 관용 파싱 표(`""`, `abc`, `0`, `-1`, `101`).
- `core/jobs/policy`: 백오프 표, 쿼터 리셋 계산(리셋 시각 경계·jitter), attempt 롤백, max 초과 시 dead 전이, `dead_retryable_alert` 임계치.
- `core/jobs/queue`: 중복 억제, 동시 클레임 시 단일 승자, 스테일 락 회수, `count_dead`.
- `core/llm/router`: 큐레이션∩헬스 순서, scouter 다운 시 정적 폴백, 429 시 다음 모델, JSON 실패 시 다음 모델, 전부 실패 시 예외 종류.
- `core/llm/chat`: `RoutingChatClient`가 `model_id`로 올바른 provider 클라이언트를 고르는지.
- `chat/use_case`: 순서 보장(가드 실패 시 크레딧 미차감, 차감 실패 시 에이전트 미호출, 에이전트 실패 시 환불 호출).
- `summary/pipeline`: 예외 분류(렌더 실패/봇 차단/파싱 실패 → 각각 다른 처리).
- `api/schemas`: `is_bookmarked` boolean 고정, `ai_summary` null 직렬화, `Paged[T]`의 `total_pages` 계산.

## 4. 통합 테스트

- `test_indexes.py`: `ensure_indexes()` 후 실제 인덱스가 [data-model.md](data-model.md)와 일치(이름·키·옵션·TTL).
- `test_job_queue.py`: 병렬 클레임, 재시도 전이 4종, 스테일 락 회수, `count_dead`, TTL 인덱스.
- `test_credits_concurrency.py`: 동시 consume → 잔액이 절대 음수가 되지 않음.
- `test_pipeline_e2e.py`: RSS 픽스처 → summary(Fake) → embedding(Fake) → Qdrant → `GET /posts`.
- `test_content_aggregator.py`: 연속 실패 시 블로그 자동 비활성화.

## 5. E2E 시나리오

로컬 스택: `docker compose -f docker/compose.dev.yml up -d mongo qdrant` + `techletter all` + 프론트 `npm run dev`(또는 빌드 후 nginx).

| 시나리오 | 검증 |
|---|---|
| 홈 진입 → 필터 조합 → 무한스크롤 | `items` 봉투, `total_pages` 기반 페이징 |
| 로그인 → 북마크 토글 → 북마크 페이지 확인 → 해제 | `/bookmarks` 경로 3개, `is_bookmarked` boolean |
| 트렌드 페이지 → 기간 변경 → 태그 선택 | `items`, 기간 파라미터 |
| 챗봇 질문 → activity 배지 → 답변 → 출처 → 크레딧 감소 표시 | SSE 3이벤트, `ChatAnswer.credits.remaining` |
| 세션 사이드바 전환 → 히스토리 로드 → 세션 삭제 | `message_count`, 평탄화 메타, 204 |
| 크레딧 0 상태에서 질문 | 402 `credit.insufficient` |
| 어드민 CRUD + 중복 등록 오류 | 201/204, 409 `details.field` |
| 어드민 운영 대시보드 → 실패 잡 재시도 → 백필 트리거 | `/admin/jobs*`, `/admin/backfill/summary` |
| 로그아웃 → 만료 토큰으로 접근 → 자동 로그아웃 | 401 인터셉터 |

각 시나리오는 실패 시 스크린샷·콘솔 로그를 남긴다. 콘솔 에러 0을 기준으로 판정한다.

## 6. CI (`.github/workflows/ci.yml`)

PR과 `develop`/`main` push에서 4개 잡이 병렬로 돈다.

| 잡 | 내용 |
|---|---|
| `check` | `ruff check`/`format --check`(ASYNC/DTZ/TID 포함) → `pyright` → 단위 테스트 → `scripts/check_routes.py`(API 계약 라우트 일치) |
| `integration` | 실제 mongo:8.0·qdrant:v1.16.2 서비스 컨테이너로 통합·계약 테스트 |
| `e2e` | `tech-letter_ui`를 체크아웃해 빌드하고, 실제 API 프로세스를 띄운 뒤 Playwright로 시나리오 실행(프론트 체크아웃 실패 시 경고만 남기고 건너뜀) |
| `images` | 런타임/브라우저 이미지 빌드 + **크기 게이트**(런타임 ≤450MB, 브라우저 ≤1200MB) + 컨테이너 안에서 `techletter version`과 필수 의존성 import 스모크 |

로컬에서 같은 검사를 하려면:
```bash
./scripts/dev.sh check   # lint → typecheck → test
```

프론트: `npm run lint`, `npm run build`.

## 7. 배포 스모크 (`scripts/verify_prod_smoke.sh`)

배포 파이프라인이 이미지를 교체한 직후 실행한다. 실패하면 자동으로 이전 이미지 태그로 되돌린다.

```
1/5 GET /health                          → 200 {"status":"ok"}
2/5 GET /api/v1/posts?page_size=1        → items/page/page_size/total/total_pages 키 존재
3/5 GET /api/v1/me (토큰 없음)             → 401
4/5 GET /api/v1/posts/{잘못된 ObjectId}   → 404, code="resource.not_found"
5/5 worker/summary-worker/embedding-worker 컨테이너 healthcheck   → healthy
```
