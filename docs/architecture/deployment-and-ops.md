# 배포 · 운영

- 운영 서버: 셀프호스팅 GitHub Actions 러너가 상주하는 ARM64 클라우드 인스턴스 한 대(라벨 `techletter-prod`).
- 인프라 compose(`mongo/qdrant/traefik`)는 별도 리포(`tech-letter_iac`)가 관리한다. 네트워크는 `tech-letter_default`.
- 배포 절차 요약은 워크스페이스 루트 `AGENTS.md`에도 기록돼 있다("변경사항 배포").

## 1. 배포 파이프라인 (`.github/workflows/deploy.yml`)

```
main push (docs/**·*.md 제외)
  1. 이미지 태그 결정 — GIT_SHA 12자
  2. 현재 실행 중인 태그 기록 (스모크 실패 시 롤백용)
  3. docker compose -f docker/compose.prod.yml build --pull   (기존 컨테이너는 계속 실행)
  4. docker compose -f docker/compose.prod.yml up -d --wait --wait-timeout 180 --remove-orphans
  5. scripts/verify_prod_smoke.sh
  6. Start 또는 Smoke 실패 → 직전 이미지 태그로 up -d 후 스모크 재실행 (자동 롤백). 직전 태그가 없거나 복구가 실패하면 명시적 오류와 함께 수동 복구 필요
  7. 성공 → 이번·직전 태그 이미지만 남기고 삭제, 7일 넘은 빌드 캐시 정리
```
- `workflow_dispatch`는 입력 없이 현재 main을 다시 배포할 뿐이다(시크릿 교체 후 재기동 용도). 옛 버전으로 되돌리는 수단이 아니다.
- compose의 `${VAR:?required}` 앵커가 빌드·기동 양쪽에서 시크릿 누락을 즉시 실패시킨다.
- `down` 없이 `up -d --wait`로 교체하므로 다운타임은 컨테이너 재생성 수 초뿐이다.
- 동시 배포는 `concurrency: production`으로 직렬화된다.
- 롤백 조건은 `failure() && (steps.start.outcome == 'failure' || steps.smoke.outcome == 'failure')`다. Start 실패로 Smoke가 skipped여도 복구하며, Build 실패는 기존 서비스가 유지되므로 롤백하지 않는다.
- 롤백은 `--no-build --pull never`로 서버에 저장된 직전 이미지만 사용한다. 이미지가 없으면 현재 소스를 옛 태그로 빌드하지 않고 실패한다. 복구 성공 후에도 원래 배포 실패는 워크플로 결과에 남는다.
- 7단계는 `techletter`·`techletter-browser` 태그 이미지 중 이번 태그와 직전 태그(다음 배포의 자동 롤백 대상)만 남긴다. 그보다 옛 버전으로 되돌리려면 `git revert` 후 재배포한다.

### 1.1 서비스 구성 (`docker/compose.prod.yml`)
| 서비스 | 이미지 | 메모리(limit/reservation) | healthcheck | Traefik |
|---|---|---|---|---|
| `api` | `techletter:${GIT_SHA}` | 640M / 256M | `curl -fsS localhost:8080/health` | `Host(tech-letter.duckdns.org) && PathPrefix(/api)` |
| `worker` | `techletter:${GIT_SHA}` | 512M / 192M | heartbeat 파일 120초 이내 | - |
| `summary_worker` | `techletter-browser:${GIT_SHA}` | 1G / 384M | heartbeat | - |
| `embedding_worker` | `techletter:${GIT_SHA}` | 640M / 256M | heartbeat | - |

공통: `restart: unless-stopped`, `logging: json-file max-size=20m max-file=5`, non-root, `networks: [tech-letter_default]`. `summary_worker`는 Chromium용 `shm_size: 256m`.

### 1.2 환경변수
전 서비스 공통(x-app-env + x-llm-env): `TZ`, `MONGO_URI`, `MONGO_DB_NAME`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION_NAME`, `LOG_LEVEL`, `JWT_SECRET`, `JWT_ISSUER`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `SUMMARY_WORKER_LLM_PROVIDER`, `SUMMARY_WORKER_LLM_MODEL_NAME`, `EMBEDDING_WORKER_LLM_PROVIDER`, `EMBEDDING_WORKER_LLM_MODEL_NAME`, `CHATBOT_LLM_PROVIDER`, `LLM_STATIC_FALLBACK_MODELS`.
`SUMMARY_WORKER_LLM_*`는 `PROVIDER`와 `MODEL_NAME` 두 변수만 compose가 주입한다. `CHATBOT_LLM_MODEL_NAME`은 사용하지 않는다.
`api`만 추가로: `SERVICE_NAME`, `API_PORT`, `GOOGLE_OAUTH_*`, `AUTH_LOGIN_SUCCESS_REDIRECT_URL`, `CORS_ALLOWED_ORIGINS`.
`worker`만 추가로: `SERVICE_NAME`, `CONTENT_BLOG_FETCH_BATCH_SIZE`. `JOB_*`는 compose가 주입하지 않으며 코드 기본값을 쓴다.
`summary_worker`만 추가로: `SERVICE_NAME`, `SUMMARY_DAILY_BUDGET`.
`embedding_worker`만 추가로: `SERVICE_NAME`. `EMBEDDING_WORKER_CHUNK_*`(2000/200)·`EMBEDDING_DAILY_CHUNK_BUDGET`(800)는 compose가 주입하지 않으며 코드 기본값을 쓴다.
`SUMMARY_SECONDARY_MODEL`·`SUMMARY_SECONDARY_DAILY_BUDGET`·`SUMMARY_PRIMARY_RPM`·`SUMMARY_SECONDARY_RPM`, `SEARCH_*`도 compose가 주입하지 않는다(코드 기본값). 운영에서 바꾸려면 `docker/compose.prod.yml`의 해당 서비스 `environment`에 먼저 추가해야 한다.

## 2. 관측 기준선

| 지표 | 확인 | 정상 |
|---|---|---|
| api 5xx | `docker logs techletter_api \| jq 'select(.status>=500)'` | 0/일 |
| 잡 큐 | `GET /admin/jobs/stats` 또는 `GET /metrics` | pending이 계속 쌓이지 않음, running ≤ 워커 수 |
| dead 사유 | `/admin/jobs?status=dead` | `permanent`(봇 차단·404)만 정상. `retryable` 누적은 조사 |
| RSS 사이클 | worker 로그 `rss cycle finished` 30분마다 | 일부 피드 상시 실패는 정상(깨진 외부 피드) |
| 요약률 | `/admin/backfill/summary` | 신규는 24시간 내 처리 |
| 임베딩 적체 | `/admin/backfill/summary`의 `unembedded`, embedding-worker 로그 `embedding daily budget exhausted` | 하루 800청크를 넘는 적체는 며칠에 걸쳐 풀린다. 정상(잡은 attempt를 안 쓰고 다음 07:00 UTC로 미뤄진다) |
| 검색 | `GET /api/v1/posts?q=카프카&page_size=1`, api 로그 `dense search failed`·`query embedding rate limited` | 200, `total>0`. 경고가 계속 나면 Gemini 한도 또는 Qdrant 확인 |
| 모델 헬스 스캔 | worker 로그 `model scan finished` 1시간마다 | `ok` 건수가 0 근처면 OpenRouter 자체 장애 의심 |
| heartbeat | compose healthcheck | healthy 4/4 |
| 메모리 | `docker stats` | §1.1의 reservation 근처에서 안정 |
| 디스크 | `docker system df` | 로그 ≤ 100MB/컨테이너(20m×5) |

`GET /metrics`(Prometheus 텍스트 노출 형식, 도커 네트워크 안에서만 접근 가능)가 잡 큐 상태를 노출한다. 스크레이퍼는 아직 없어 `docker exec techletter_api curl localhost:8080/metrics`로 수동 확인한다. `dead`이면서 `error_kind=retryable`인 잡이 임계치(`JOB_DEAD_RETRYABLE_ALERT_THRESHOLD`, 기본 5)를 넘으면 `worker`가 구조화 로그로 경고를 남긴다 — `docker logs techletter_worker | grep WARNING`으로 확인한다. 진짜 페이징 알림이 필요하면 Prometheus/Alertmanager 같은 별도 스택이 있어야 하는데, 이 서버엔 아직 없다.

## 3. 런북

- **실패 잡 처리**: 어드민 운영 대시보드 또는 `techletter jobs list --status dead`. 사유가 `permanent`(봇 차단·404)면 재시도가 무의미하다 → 블로그 설정 수정 또는 비활성화. 일시 장애면 `jobs retry`.
- **요약 백필**: `techletter backfill summaries --limit N --priority 10 --dry-run` → 실행. 신규 포스트(priority 0)가 항상 먼저 처리된다.
- **무료 모델 소멸**: 모델 라우터가 헬스 상위 모델로 자동 폴백하므로 조치가 필요 없다.
- **LLM 일일 예산 소진**: 정상 동작이다. 요약은 3 Flash(20) → 3.5 Flash Lite(450) → OpenRouter 순으로 흐르고, 다음 리셋(`LLM_QUOTA_RESET_UTC_HOUR`=07:00 UTC)에 다시 1순위 모델을 쓴다. 오늘 쓴 양(키 `google`·`google:gemini-3.5-flash-lite`·`gemini-embedding-chunks`):
  ```bash
  ssh oracle-ampere-a1-instance-free 'docker exec techletter_mongo mongosh -u root -p "$(docker exec techletter_mongo printenv MONGO_INITDB_ROOT_PASSWORD)" --authenticationDatabase admin techletter --quiet --eval "db.llm_daily_usage.find().sort({updated_at:-1}).limit(5).toArray()"'
  ```
- **임베딩 쿼터로 dead가 된 잡** (`error_kind=quota`, 쿼터 대기 누적 120시간 초과): 블로그를 한꺼번에 추가한 뒤에 생긴다. 쿼터가 풀린 뒤 다시 건다 — 재시도하면 누적 대기가 0으로 돌아간다.
  ```bash
  ssh oracle-ampere-a1-instance-free 'docker exec techletter_worker techletter jobs list --status dead'   # 사유 확인
  ssh oracle-ampere-a1-instance-free 'docker exec techletter_worker techletter jobs retry --type embedding.requested --kind quota --limit 500'
  ```
  어드민 API로는 `POST /admin/jobs/retry-bulk {"type":"embedding.requested","error_kind":"quota","limit":500}`. 한꺼번에 살려도 하루 800청크씩만 처리되고 나머지는 다시 쿼터 대기로 돈다. 2026-09-26에 한도가 30시간이던 때 블로그 11곳 추가 후 170건이 이렇게 죽었다(그래서 120시간으로 늘렸다).
- **새 글이 검색에 안 나옴**: 어휘 색인 잡(`search.lexical_index_requested`, embedding-worker)이 밀렸는지 본다. 급하면 `techletter backfill lexical --execute`(Gemini 호출 없음, 수 초). `--dry-run`은 대상 수와 실측 평균 문서 길이를 보여 준다 — `AVG_DOC_LENGTH`(170)와 크게 벌어지면 상수를 고치고 재백필([search.md](search.md) §2).
- **블로그 아이콘**: 새 블로그는 등록 시 자동으로 수집 잡이 걸린다. 한 번도 시도 안 한 블로그 일괄: `techletter backfill icons --dry-run` → `--execute`(`--all`이면 전부 다시). 못 받은 블로그(Medium 등)는 어드민 블로그 탭에서 직접 올리거나 "주소에서 받기"로 회사 홈페이지 주소를 준다. 브라우저는 1시간 캐시하므로 바꾼 아이콘은 최대 1시간 뒤 보인다.
- **모델 헬스 기록 없음/오래됨**: 라우터가 정적 폴백 목록으로 계속 동작한다. `docker logs techletter_worker | grep "model scan"`으로 스캔이 도는지 확인한다.
- **블로그 피드 장애**: 어드민에서 `last_fetch_error` 확인 → RSS URL 수정 또는 `is_active=false`. 실패 48회가 누적되고 마지막 회차가 `PermanentError`(HTTP 400/401/403/404/410/451)일 때만 자동으로 비활성화된다. 5xx나 타임아웃만으로는 꺼지지 않는다.
- **LLM 키 교체**: GitHub Environment secret 갱신 → `deploy.yml`을 `workflow_dispatch`로 재실행.
- **Mongo 백업**: `mongodump --archive --gzip` 정기 백업을 권장한다.
- **Mongo가 SPOF**: 잡 큐까지 Mongo에 있으므로 Mongo 장애는 전면 정지로 이어진다. 볼륨 백업과 `restart: unless-stopped`에 의존하는 트레이드오프를 이 규모에서는 수용한다.
- **알려진 제약**: IaC의 Mongo/mongo-express 비밀번호가 평문으로 관리되고 있다. 교체 시 `MONGO_URI` secret도 함께 갱신해야 한다.

### 3.1 수동 데이터 작업 기록
- **2026-09-27 중복 포스트 정리**: 블로그가 도메인·URL을 옮기면서 같은 글이 새 링크로 다시 들어온 것이 46건(같은 블로그·같은 제목). 2026-09-25 옮긴 글 감지(`79664e5` — 같은 블로그에 제목과 마지막 경로 조각이 같은 글이 있으면 새로 넣지 않고 링크만 바꾼다) 이전에 쌓인 것들이다. **오래된 쪽 포스트를 남기고** 새 쪽을 합친 뒤, 남긴 포스트의 링크를 가장 최신 URL로 바꿨다. 작업 전 백업: 서버 `/home/ubuntu/backups/mongo-20260927-064602-before-dedupe`. 이후 재발은 수집기 감지가 막는다 — 다시 보이면 감지 규칙(`content/rss/aggregator.py`, `content/links.py`)이 못 잡는 URL 변경 패턴이다.

## 4. 롤백

- **배포 기동 또는 스모크 실패**: 파이프라인이 같은 실행 안에서 직전 이미지 태그로 되돌리고 스모크를 재실행한다. `Start` 실패와 `Smoke` 실패를 각각 확인하므로 Smoke가 skipped인 경우도 복구한다. Build 실패는 롤백 대상이 아니다.
- **자동 복구 불가**: 직전 태그가 없거나, 직전 이미지 기동 또는 롤백 후 스모크가 실패하면 명시적 오류를 남긴다. 컨테이너 상태·로그와 보존된 이미지 태그를 확인해 수동 복구한다. 취소·러너 중단으로 워크플로 자체가 실행되지 못한 경우도 수동 확인이 필요하다.
- **배포는 성공했지만 나중에 문제가 발견된 경우**: 해당 커밋을 되돌리고 다시 push한다.
  ```bash
  git revert --no-edit <bad-sha> && git push origin main
  ```
  이미지 태그가 커밋 SHA이므로 재빌드는 몇 분이면 끝난다.

## 5. 로컬 개발
```bash
uv sync
docker compose -f docker/compose.dev.yml up -d mongo qdrant
cp .env.example .env && $EDITOR .env
uv run techletter ensure-indexes
uv run techletter all --reload            # api + worker
uv run techletter summary-worker          # 별도 터미널(playwright install 필요)
./scripts/dev.sh test / ./scripts/dev.sh lint / ./scripts/dev.sh typecheck
```
프론트: `VITE_API_BASE_URL=http://localhost:8080 npm run dev`. E2E는 [testing-strategy.md](testing-strategy.md).
