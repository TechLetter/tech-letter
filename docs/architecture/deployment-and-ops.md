# 배포 · 운영

- 운영 서버: 셀프호스팅 GitHub Actions 러너가 상주하는 ARM64 클라우드 인스턴스 한 대(라벨 `techletter-prod`).
- 인프라 compose(`mongo/qdrant/traefik`)는 별도 리포(`tech-letter_iac`)가 관리한다. 네트워크는 `tech-letter_default`.
- 배포 절차 요약은 워크스페이스 루트 `AGENTS.md`에도 기록돼 있다("변경사항 배포").

## 1. 배포 파이프라인 (`.github/workflows/deploy.yml`)

```
main push (docs/**·*.md 제외)
  1. 이미지 태그 결정 — GIT_SHA 12자, 또는 workflow_dispatch의 image_tag 입력
  2. 현재 실행 중인 태그 기록 (스모크 실패 시 롤백용)
  3. docker compose -f docker/compose.prod.yml build --pull   (기존 컨테이너는 계속 실행)
  4. docker compose -f docker/compose.prod.yml up -d --wait --wait-timeout 180 --remove-orphans
  5. scripts/verify_prod_smoke.sh
  6. 실패 → 직전 이미지 태그로 up -d 후 스모크 재실행 (자동 롤백)
  7. 성공 → 168시간 넘은 이미지 정리
```
- 이미지 태그가 커밋 SHA이므로 임의 시점으로 재배포할 수 있다.
- compose의 `${VAR:?required}` 앵커가 빌드·기동 양쪽에서 시크릿 누락을 즉시 실패시킨다.
- `down` 없이 `up -d --wait`로 교체하므로 다운타임은 컨테이너 재생성 수 초뿐이다.
- 동시 배포는 `concurrency: production`으로 직렬화된다.

### 1.1 서비스 구성 (`docker/compose.prod.yml`)
| 서비스 | 이미지 | 메모리(limit/reservation) | healthcheck | Traefik |
|---|---|---|---|---|
| `api` | `techletter:${GIT_SHA}` | 640M / 256M | `curl -fsS localhost:8080/health` | `Host(tech-letter.duckdns.org) && PathPrefix(/api)` |
| `worker` | `techletter:${GIT_SHA}` | 512M / 192M | heartbeat 파일 120초 이내 | - |
| `summary_worker` | `techletter-browser:${GIT_SHA}` | 1G / 384M | heartbeat | - |
| `embedding_worker` | `techletter:${GIT_SHA}` | 640M / 256M | heartbeat | - |

공통: `restart: unless-stopped`, `logging: json-file max-size=20m max-file=5`, non-root, `networks: [tech-letter_default]`. `summary_worker`는 Chromium용 `shm_size: 256m`.

### 1.2 환경변수
공통: `MONGO_URI`, `MONGO_DB_NAME`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION_NAME`, `LOG_LEVEL`, `SUMMARY_WORKER_LLM_*`, `EMBEDDING_WORKER_LLM_*`, `CHATBOT_LLM_*`, `CHATBOT_EMBEDDING_*`, `*_MODEL_PREFERENCE`, `LLM_STATIC_FALLBACK_MODELS`.
`api`만 추가로: `JWT_SECRET`, `JWT_ISSUER`, `GOOGLE_OAUTH_*`, `AUTH_LOGIN_SUCCESS_REDIRECT_URL`, `CORS_ALLOWED_ORIGINS`.
`worker`만 추가로: `CONTENT_BLOG_FETCH_BATCH_SIZE`, `JOB_*`.
`summary_worker`만 추가로: `RENDERER_STRATEGY`, `SCRAPERAPI_KEY`, `SUMMARY_DAILY_BUDGET`.
`embedding_worker`만 추가로: `EMBEDDING_WORKER_CHUNK_*`.

## 2. 관측 기준선

| 지표 | 확인 | 정상 |
|---|---|---|
| api 5xx | `docker logs techletter_api \| jq 'select(.status>=500)'` | 0/일 |
| 잡 큐 | `GET /admin/jobs/stats` 또는 `GET /metrics` | pending이 계속 쌓이지 않음, running ≤ 워커 수 |
| dead 사유 | `/admin/jobs?status=dead` | `permanent`(봇 차단·404)만 정상. `retryable` 누적은 조사 |
| RSS 사이클 | worker 로그 `rss cycle completed` 30분마다 | 일부 피드 상시 실패는 정상(깨진 외부 피드) |
| 요약률 | `/admin/backfill/summary` | 신규는 24시간 내 처리 |
| 모델 성적 | `/admin/llm-models` | 1순위 성공률 ≥ 0.8, 강등 발생 시 선호 목록 재검토 |
| 모델 헬스 스캔 | worker 로그 `model scan complete` 1시간마다 | `ok` 건수가 0 근처면 OpenRouter 자체 장애 의심 |
| heartbeat | compose healthcheck | healthy 4/4 |
| 메모리 | `docker stats` | §1.1의 reservation 근처에서 안정 |
| 디스크 | `docker system df` | 로그 ≤ 100MB/컨테이너(20m×5) |

`GET /metrics`(Prometheus 텍스트 노출 형식, 도커 네트워크 안에서만 접근 가능)가 잡 큐 상태를 노출한다. 스크레이퍼는 아직 없어 `docker exec techletter_api curl localhost:8080/metrics`로 수동 확인한다. `dead`이면서 `error_kind=retryable`인 잡이 임계치(`JOB_DEAD_RETRYABLE_ALERT_THRESHOLD`, 기본 5)를 넘으면 `worker`가 구조화 로그로 경고를 남긴다 — `docker logs techletter_worker | grep WARNING`으로 확인한다. 진짜 페이징 알림이 필요하면 Prometheus/Alertmanager 같은 별도 스택이 있어야 하는데, 이 서버엔 아직 없다.

## 3. 런북

- **실패 잡 처리**: 어드민 운영 대시보드 또는 `techletter jobs list --status dead`. 사유가 `permanent`(봇 차단·404)면 재시도가 무의미하다 → 블로그 설정 수정 또는 비활성화. 일시 장애면 `jobs retry`.
- **요약 백필**: `techletter backfill summaries --limit N --priority 10 --dry-run` → 실행. 신규 포스트(priority 0)가 항상 먼저 처리된다.
- **무료 모델 소멸**: 모델 라우터가 자동으로 폴백하므로 조치가 필요 없다. `/admin/llm-models`에서 성적을 확인하고 `*_MODEL_PREFERENCE`를 갱신하면 더 나은 후보를 우선순위에 둘 수 있다.
- **LLM 일일 예산 소진**: 정상 동작이다. 초과분은 OpenRouter로 흐르고, 다음 리셋(`LLM_QUOTA_RESET_UTC_HOUR`)에 다시 1순위 모델을 쓴다.
- **모델 헬스 기록 없음/오래됨**: 라우터가 정적 폴백 목록으로 계속 동작한다. `docker logs techletter_worker | grep "model scan"`으로 스캔이 도는지 확인한다.
- **블로그 피드 장애**: 어드민에서 `last_fetch_error` 확인 → RSS URL 수정 또는 `is_active=false`. 연속 실패가 임계치를 넘으면 자동으로 비활성화된다.
- **LLM 키 교체**: GitHub Environment secret 갱신 → `deploy.yml`을 `workflow_dispatch`로 재실행.
- **Mongo 백업**: `mongodump --archive --gzip` 정기 백업을 권장한다.
- **Mongo가 SPOF**: 잡 큐까지 Mongo에 있으므로 Mongo 장애는 전면 정지로 이어진다. 볼륨 백업과 `restart: unless-stopped`에 의존하는 트레이드오프를 이 규모에서는 수용한다.
- **알려진 제약**: IaC의 Mongo/mongo-express 비밀번호가 평문으로 관리되고 있다. 교체 시 `MONGO_URI` secret도 함께 갱신해야 한다.

## 4. 롤백

- **배포 직후 스모크 실패**: 파이프라인이 같은 실행 안에서 자동으로 직전 이미지 태그로 되돌리고 스모크를 재실행한다. 사람이 할 일은 검증뿐이다.
- **배포는 성공했지만 나중에 문제가 발견된 경우**: 해당 커밋을 되돌리고 다시 push한다.
  ```bash
  git revert --no-edit <bad-sha> && git push origin main
  ```
  이미지 태그가 커밋 SHA이므로 재빌드는 몇 분이면 끝난다. 급하면 `workflow_dispatch`로 알려진 좋은 SHA를 `image_tag`에 지정해 재배포할 수도 있다.

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
