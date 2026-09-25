# API 계약

경로 prefix는 `/api/v1`. 이 문서가 구현 스펙이자 계약 테스트의 원본이다.

## 1. 공통 규약

### 1.1 전송
- `application/json; charset=utf-8`, 키는 snake_case.
- 시간은 오프셋 포함 ISO-8601 UTC, 밀리초 포함 — `2026-08-28T09:15:00.000Z`.
- 배열 쿼리는 반복 키(`?tags=a&tags=b`)로 받는다.
- 빈 문자열 쿼리 파라미터는 "값 없음"으로 취급하고 무시한다.
- 숫자 쿼리 파싱에 실패하면(`page=abc`) 기본값으로 대체하고 422를 내지 않는다.

### 1.2 목록 봉투
```json
{
  "items": [ … ],
  "page": 1,
  "page_size": 20,
  "total": 137,
  "total_pages": 7
}
```
모든 목록 응답이 이 형태다. 페이지네이션이 의미 없는 응답(필터 목록 등)은 `page`/`page_size`/`total_pages`를 생략하고 `{items, total}`만 반환한다.

### 1.3 에러 봉투
```json
{
  "error": {
    "code": "credit.insufficient",
    "message": "크레딧이 부족합니다. 내일 다시 시도해 주세요.",
    "details": { "remaining": 0 }
  }
}
```
- `code`는 아래 카탈로그의 문자열. 프론트는 이 값만 분기한다.
- `message`는 사용자 표시용 한국어.
- `details`는 선택(어드민 중복 오류의 `field`, 크레딧 잔량 등).
- 삭제 성공은 `204`, 생성/변경 성공은 리소스를 반환한다(`{"message": "..."}` 같은 문자열 봉투는 쓰지 않는다).
- SSE `error` 이벤트도 같은 봉투를 쓴다.

### 1.4 에러 코드 카탈로그
| code | HTTP | 의미 |
|---|---|---|
| `request.invalid` | 400 | 본문/파라미터 형식 오류 |
| `auth.required` | 401 | 토큰 없음/형식 오류/빈 토큰 |
| `auth.invalid_token` | 401 | 서명·만료 오류 |
| `auth.forbidden` | 403 | 어드민 권한 부족 |
| `auth.session_expired` | 400 | 로그인 세션 교환 실패 |
| `resource.not_found` | 404 | 대상 없음 |
| `resource.conflict` | 409 | 중복(`details.field`: `rss_url` \| `url` \| `text` \| `link`) |
| `credit.insufficient` | 402 | 크레딧 부족 |
| `credit.error` | 500 | 크레딧 처리 실패 |
| `chat.session_not_found` | 400 | session_id 무효 |
| `policy.blocked` | 403 | 프롬프트 가드 차단 |
| `llm.rate_limited` | 429 | 챗봇 모델 후보가 모두 rate limit/쿼터 소진 |
| `llm.unavailable` | 503 | 챗봇 모델 후보가 모두 실패/장애 |
| `internal.error` | 500 | 그 외 |

### 1.5 상태 코드
| 상황 | 코드 |
|---|---|
| 조회 성공 | 200 |
| 생성 성공 | 201 + 생성된 리소스 |
| 변경 성공 | 200 + 변경된 리소스 |
| 삭제 성공 | 204, 본문 없음 |
| 액션 성공(요약 트리거 등) | 202 Accepted + `{"job_id": "…"}` |

### 1.6 인증
`Authorization: Bearer <JWT>`, HS256, 클레임 `sub/role/iss/exp`(24h). 쿠키는 OAuth `oauth_state`(300초, HttpOnly, 운영에서 `Secure`)만 쓴다.

`user_code`가 path에 오는 어드민 경로(`/admin/users/{user_code}/credits`)는 프론트가 `encodeURIComponent`를 적용해서 보낸다.

## 2. 리소스 스키마

### 2.1 `Post`
```json
{
  "id": "6a83a8f5d34e63d870811f92",
  "blog_id": "68f1...", "blog_name": "카카오",
  "title": "…", "link": "https://…",
  "published_at": "2026-08-18T00:22:25.000Z",
  "thumbnail_url": "https://…",
  "view_count": 12,
  "summary": "…",
  "categories": ["백엔드"],
  "tags": ["Kafka", "MSA"],
  "is_bookmarked": false
}
```
`is_bookmarked`는 항상 boolean(익명 요청이면 `false`). `categories`/`tags`는 항상 배열(요약 전이면 `[]`). `summary`/`thumbnail_url`은 없으면 `null`.

### 2.2 `AdminBlog`
`{id, name, url, rss_url, is_active, post_count, consecutive_failures, last_fetched_at, last_fetch_error, created_at, updated_at}`. `last_fetch_error`는 최대 200자로 절단해서 저장한다. 실패 48회가 누적되고 마지막 회차가 `PermanentError`(HTTP 400/401/403/404/410/451)일 때만 블로그가 자동으로 `is_active=false`가 된다. 5xx·타임아웃만으로는 비활성화하지 않는다.

### 2.3 `AdminPost`
```json
{
  "id": "…", "title": "…", "link": "…", "blog_id": "…", "blog_name": "…",
  "published_at": "…", "thumbnail_url": null, "view_count": 0,
  "status": { "summarized": true, "embedded": true, "failed_reason": null },
  "ai_summary": { "summary": "…", "categories": [], "tags": [],
                  "model_name": "gemini-3-flash-preview",
                  "generated_at": "…" },
  "embedding": { "model_name": "gemini-embedding-001",
                 "collection_name": "tech_letter_posts__gemini-embedding-001__3072",
                 "vector_dimension": 3072, "chunk_count": 20,
                 "embedded_at": "…" },
  "created_at": "…", "updated_at": "…"
}
```
`ai_summary`/`embedding`은 없으면 `null`. `status.failed_reason`은 요약이 영구 실패(`PermanentError`)로 죽었을 때 그 사유를 담는다.

### 2.4 `Me`
```json
{
  "user_code": "google:…", "email": "…", "name": "…",
  "role": "user",
  "credits": { "remaining": 7, "granted_today": 10 },
  "created_at": "…", "updated_at": "…"
}
```
`credits.granted_today`는 오늘(UTC) 지급된 크레딧 총량(`daily` + `admin_grant` 합계)이며, 소비·환불은 제외한다.

### 2.5 `ChatSession`
```json
{
  "id": "…", "title": "…",
  "created_at": "…", "updated_at": "…",
  "messages": [
    { "role": "user", "content": "…", "created_at": "…" },
    { "role": "assistant", "content": "…", "created_at": "…",
      "sources": [ {"post_id":"…","title":"…","blog_name":"…","link":"…"} ],
      "agent":  {"mode":"…","intent":"…","model_id":null,"activities":[…]},
      "guard":  {"action":"pass","message":null},
      "memory": {"used":true,"status":"ready","compressed":false} }
  ]
}
```
목록 응답(`GET /chat/sessions`)은 `messages`를 `null`로 준다. 메시지 메타데이터(`sources`/`agent`/`guard`/`memory`)는 평탄화되어 있다.

### 2.6 `ChatAnswer` (`POST /chat/messages` 응답 및 SSE `done`)
```json
{
  "session_id": "…",
  "message_id": "…",
  "answer": "마크다운 …",
  "sources": [ {"post_id":"…","title":"…","blog_name":"…","link":"…","score":0.83} ],
  "agent":  {"mode":"…","intent":"…","model_id":null,"activities":[{"type":"search","label":"…","status":"done"}]},
  "guard":  {"action":"pass","risk_level":"low","message":null,"findings":[]},
  "memory": {"used":true,"status":"ready","compressed":false,"compression_failed":false,"recent_message_count":6},
  "credits": {"consumed":1,"remaining":6}
}
```
`agent.model_id`는 실제 사용 모델 ID(`string|null`)이며, 알 수 없으면 `null`이다.
`guard.action ∈ {pass, sanitize, block}`, `memory.status ∈ {ready, pending, failed}`.

### 2.7 Trends
- `GET /trends/weekly` → `{"period": {from_at, to, previous_from, previous_to}, "post_count": n, "blog_count": n, "items": [{topic, blog_count, post_count, previous_blog_count, previous_post_count, posts: Post[≤3]}]}`
  - 최근 7일 대 직전 7일. 주제(`categories`) 단위로 **다룬 회사 수** 순으로 정렬하고 `기타`는 뺀다. 대표 글은 최근 글부터, 회사가 겹치지 않게 고른다.

### 2.8 Filters
`{"items": [{"name": "백엔드", "count": 12}], "total": 8}` / 블로그는 `{"id","name","count"}`.

### 2.9 `Job` (어드민 운영 대시보드)
```json
{
  "id": "…", "type": "summary.requested", "key": "<post_id>",
  "status": "dead", "attempt": 5, "max_attempt": 5,
  "priority": 0,
  "run_at": "…", "last_error": "ai judged that this content is not summarizable: …",
  "error_kind": "permanent",
  "created_at": "…", "updated_at": "…", "finished_at": "…"
}
```

### 2.10 `LlmModelPreference` (어드민)
```json
{ "purpose": "summary",
  "models": ["nvidia/nemotron-3-super-120b-a12b:free"],
  "source": "settings", "default_models": ["nvidia/nemotron-3-super-120b-a12b:free"] }
```
`default_models`는 `SUMMARY_MODEL_PREFERENCE`에서 온 기본 후보이고, `models`는
환경변수 기본 후보 뒤에 어드민이 DB에 저장한 추가 후보를 붙인 최종 순서다(중복 제거).
`source`는 DB 추가 후보가 있으면 `database`, 없으면 `settings`다. 챗봇·플래너에는
선호목록이 없다.

### 2.11 모델 상태(공개)
어드민용과 달리 테크레터 내부 실사용 성적(`json_failures`·`rate_limited`·성공률)은 없다 — OpenRouter 쪽 헬스만 보여준다.
```json
// GET /llm-models/summary
{ "total_models": 42, "healthy_count": 30, "degraded_count": 8, "down_count": 4,
  "last_checked_at": "…" }
// GET /llm-models → items: ModelHealth[]
{ "model_id": "nvidia/nemotron-3-super-120b-a12b:free", "state": "healthy",
  "uptime_24h": 96.5, "uptime_30d": 97.2, "avg_latency_ms": 1180, "consecutive_failures": 0,
  "latest_status": "OK", "daily": [{ "date": "2026-09-06", "uptime": 95.8 }] }
```
`state ∈ {healthy, degraded, down}` — 24시간 가용률 90% 이상 / 50% 이상 / 그 미만(요약 숫자와 같은 기준). `daily`는 최근 30일, 오래된 날부터이며 기록이 없는 날은 빠진다.

## 3. 엔드포인트

### 3.1 공개
| 메서드 | 경로 | 인증 | 쿼리/바디 | 응답 |
|---|---|---|---|---|
| GET | `/health` | - | | `200 {"status":"ok"}` / `503 {"status":"degraded","checks":{...}}` (Traefik은 `/api`만 라우팅하므로 compose healthcheck 전용) |
| GET | `/posts` | 선택 | `page, page_size, categories[], tags[], blog_id, published_from, published_to` | 목록 봉투 + `Post[]` |
| GET | `/posts/{id}` | 선택 | | `Post` / 404 `resource.not_found` |
| POST | `/posts/{id}/views` | - | | `204` |
| GET | `/bookmarks` | 필수 | `page, page_size` | 목록 + `Post[]`(`is_bookmarked: true`) |
| POST | `/bookmarks` | 필수 | `{post_id}` | `201 {post_id, created_at}`(중복도 멱등 upsert) / 404 |
| DELETE | `/bookmarks/{post_id}` | 필수 | | `204` / 404 |
| GET | `/filters/categories` | - | `blog_id, tags[]` | `{items,total}` |
| GET | `/filters/tags` | - | `blog_id, categories[]` | `{items,total}` |
| GET | `/filters/blogs` | - | `categories[], tags[]` | `{items,total}` |
| GET | `/trends/weekly` | - | `limit`(기본 8, 최대 30) | 2.7 |
| GET | `/llm-models/summary` | - | | 2.11 |
| GET | `/llm-models` | - | | 목록 + `ModelHealth[]`(2.11) |

공개 `/posts`는 요약이 완료된 포스트만 반환한다.

### 3.2 인증 / 나
| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/auth/google/login` | | 302 → Google (state 쿠키 300s) |
| GET | `/auth/google/callback` | `state, code` | 302 → `{FRONT}/login/success?session=…`. 모든 실패도 302(쿼리 없음) |
| POST | `/auth/token` | `{session}` | `200 {access_token, token_type:"Bearer", expires_in:86400}` / 400 `auth.session_expired` |
| GET | `/me` | | `Me` |
| DELETE | `/me` | | `204` |

### 3.3 채팅
| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/chat/suggested-questions` | | `{items:[{id,text}],total}` |
| GET | `/chat/sessions` | `page, page_size` | 목록 + `ChatSession[]`(messages 제외, `updated_at` desc) |
| POST | `/chat/sessions` | | `201 ChatSession` |
| GET | `/chat/sessions/{id}` | | `ChatSession`(messages 포함) / 400 `chat.session_not_found` |
| DELETE | `/chat/sessions/{id}` | | `204` / 400 `chat.session_not_found` |
| POST | `/chat/messages` | `{query, session_id?, model_id?}` | `200 ChatAnswer` |
| POST | `/chat/messages/stream` | `{query, session_id?, model_id?}` | SSE |

처리 순서: 프롬프트 가드 → 세션 검증 → 크레딧 1 차감 → 에이전트 → 성공 시 메시지 저장 / 실패 시 환불.
`model_id`는 선택 필드이며 무료 모델 카탈로그에 있는 id만 허용한다. 생략하면 자동으로
모델을 고른다. 유효하지 않은 id는 400 `request.invalid`(`details.field="model_id"`)다.
에러: `policy.blocked`(403) · `chat.session_not_found`(400) · `credit.insufficient`(402) · `llm.rate_limited`(429) · `llm.unavailable`(503).

### 3.4 어드민 (`role=admin`)
| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/admin/posts` | `page, page_size, summarized?, embedded?, blog_id?, q?` | 목록 + `AdminPost[]` |
| POST | `/admin/posts` | `{blog_id, title, link}` | `201 AdminPost` / 409 |
| DELETE | `/admin/posts/{id}` | | `204` |
| POST | `/admin/posts/{id}/summarize` | | `202 {job_id}` |
| POST | `/admin/posts/{id}/embed` | | `202 {job_id}` |
| GET | `/admin/blogs` | `page, page_size, is_active?` (`없음/인식불가`=전체, `true`=활성만, `false`=비활성만) | 목록 + `AdminBlog[]` |
| POST | `/admin/blogs` | `{name,url,rss_url,is_active}` | `201 AdminBlog` / 409 `details.field` |
| PUT | `/admin/blogs/{id}` | 동일 | `200 AdminBlog` |
| DELETE | `/admin/blogs/{id}` | `delete_posts=bool` | `200 {deleted_posts: n}` |
| POST | `/admin/blogs/{id}/activate` | | `200 AdminBlog`(자동 비활성화 해제, `post_count` 실제 카운트) |
| GET | `/admin/users` | `page, page_size` | 목록 + `{user_code,email,name,role,credits:{remaining,granted_today},created_at,updated_at}` |
| POST | `/admin/users/{user_code}/credits` | `{amount, expires_at}` (`expires_at ≤ now+365일`) | `201 {user_code, amount, expires_at}` / 400 `request.invalid` (`details.field="expires_at"`, `details.max_days=365`) |
| GET | `/admin/suggested-questions` | `include_inactive` | 목록(페이지네이션 없음) |
| POST | `/admin/suggested-questions` | `{text, sort_order, is_active}` | `201` / 409 `details.field="text"` |
| PUT | `/admin/suggested-questions/{id}` | 동일 | `200` |
| DELETE | `/admin/suggested-questions/{id}` | | `204` |
| GET | `/admin/jobs` | `status?`(pending\|running\|done\|dead), `type?, page, page_size` | 목록 + `Job[]` |
| GET | `/admin/jobs/stats` | | `{by_status:{pending,running,done,dead}, by_type:{…}, oldest_pending_at}` |
| POST | `/admin/jobs/{id}/retry` | | `200 Job`(status→pending, attempt→0) |
| POST | `/admin/jobs/retry-bulk` | `{type?, error_kind?, limit}` | `200 {retried: n}` |
| DELETE | `/admin/jobs/{id}` | | `204` |
| GET | `/admin/llm-models/preferences` | | 목록(요약 1건) + `{purpose, models, source, default_models}` |
| PUT | `/admin/llm-models/preferences/{purpose}` | `{models:[]}` (`purpose=summary`) | `{purpose, models, source, default_models}` |
| GET | `/admin/backfill/summary` | | `{unsummarized, unembedded, pending_jobs, dead_jobs}` |
| POST | `/admin/backfill/summary` | `{limit, priority}` | `202 {enqueued: n}` |
| POST | `/admin/backfill/embeddings` | `{limit, priority}` | `202 {enqueued: n}` |

## 4. SSE 와이어 포맷 (`POST /chat/messages/stream`)

- 헤더: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- 이벤트 이름: `activity` · `done` · `error`.
- `activity` data: `{type, label, status}`(`status ∈ {running, done, failed}`).
- `done` data: `ChatAnswer`(2.6).
- `error` data: `{"error": {"code","message","details"}}`(에러 봉투와 동일).
- 스트림 시작 전 실패(가드/세션/크레딧)는 SSE가 아닌 JSON 에러 응답으로 즉시 반환한다.
- 15초마다 `: keepalive` 주석 프레임을 보낸다(프록시 타임아웃 방지). 프론트 파서는 `data:` 없는 블록을 무시한다.

## 5. 어드민 운영 대시보드

프론트 `/admin`에서 운영 관련 기능은 다음 두 탭으로 제공된다.
1. **운영(Ops)**: 잡 큐 상태 카드(pending/running/dead), 타입별 분포, 가장 오래된
   pending, 실패 잡 목록(사유·attempt·재시도 버튼), 일괄 재시도, 백필 트리거.
2. **모델**: 모델 성적 통계 표는 제공하지 않으며, 요약 모델 폴백 체인(칩 추가/삭제/
   순서 변경)을 `/admin/llm-models/preferences` API로 조회·저장한다.
