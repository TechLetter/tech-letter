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
| `resource.conflict` | 409 | 중복(`details.field`: `rss_url` \| `url` \| `text`) |
| `credit.insufficient` | 402 | 크레딧 부족 |
| `credit.error` | 500 | 크레딧 처리 실패 |
| `chat.session_not_found` | 400 | session_id 무효 |
| `policy.blocked` | 403 | 프롬프트 가드 차단 |
| `llm.rate_limited` | 429 | 모델 전부 rate limit |
| `llm.unavailable` | 503 | 모델 전부 실패/장애 |
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

### 2.2 `Blog` / `AdminBlog`
공개: `{id, name, url}`.
어드민: `{id, name, url, rss_url, blog_type, is_active, tls_insecure, post_count, consecutive_failures, last_fetched_at, last_fetch_error, created_at, updated_at}`. `last_fetch_error`는 최대 200자로 절단해서 저장한다. `consecutive_failures`가 임계치를 넘으면 블로그가 자동으로 `is_active=false`가 된다.

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
  "profile_image": "https://…", "role": "user",
  "credits": { "remaining": 7, "granted_today": 10 },
  "created_at": "…", "updated_at": "…"
}
```

### 2.5 `ChatSession`
```json
{
  "id": "…", "title": "…",
  "message_count": 8,
  "created_at": "…", "updated_at": "…",
  "messages": [
    { "role": "user", "content": "…", "created_at": "…" },
    { "role": "assistant", "content": "…", "created_at": "…",
      "sources": [ {"post_id":"…","title":"…","blog_name":"…","link":"…"} ],
      "agent":  {"mode":"…","intent":"…","activities":[…]},
      "guard":  {"action":"pass","message":null},
      "memory": {"used":true,"status":"ready","compressed":false} }
  ]
}
```
목록 응답(`GET /chat/sessions`)은 `messages`를 제외하고 `message_count`만 포함한다. 메시지 메타데이터(`sources`/`agent`/`guard`/`memory`)는 평탄화되어 있다.

### 2.6 `ChatAnswer` (`POST /chat/messages` 응답 및 SSE `done`)
```json
{
  "session_id": "…",
  "message_id": "…",
  "answer": "마크다운 …",
  "sources": [ {"post_id":"…","title":"…","blog_name":"…","link":"…","score":0.83} ],
  "agent":  {"mode":"…","intent":"…","activities":[{"type":"search","label":"…","status":"done"}]},
  "guard":  {"action":"pass","risk_level":"low","message":null,"findings":[]},
  "memory": {"used":true,"status":"ready","compressed":false,"compression_failed":false,"recent_message_count":6},
  "credits": {"consumed":1,"remaining":6}
}
```
`guard.action ∈ {pass, sanitize, block}`, `memory.status ∈ {ready, pending, failed}`.

### 2.7 Trends
- `GET /trends/rising` → `{"period": {...}, "items": [{tag, current_count, previous_count, delta, growth_rate}], "total": n}`
- `GET /trends/series` → `{"period": {...}, "items": [{tag, points: [{bucket, post_count, blog_count}]}]}`
- `GET /trends/posts` → 표준 목록 봉투 + `Post` 배열

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
  "trace_id": "…", "created_at": "…", "updated_at": "…", "finished_at": "…"
}
```

### 2.10 `LlmModelStat` (어드민)
```json
{ "model_id": "nvidia/nemotron-3-super-120b-a12b:free", "purpose": "summary",
  "attempts": 42, "successes": 39, "json_failures": 2, "rate_limited": 1,
  "success_rate": 0.93, "avg_latency_ms": 1180,
  "healthy": true, "uptime_24h": 100.0,
  "last_used_at": "…", "last_error": null }
```

## 3. 엔드포인트

### 3.1 공개
| 메서드 | 경로 | 인증 | 쿼리/바디 | 응답 |
|---|---|---|---|---|
| GET | `/health` | - | | `200 {"status":"ok"}` / `503 {"status":"degraded","checks":{...}}` |
| GET | `/posts` | 선택 | `page, page_size, categories[], tags[], blog_id, published_from, published_to` | 목록 봉투 + `Post[]` |
| GET | `/posts/{id}` | 선택 | | `Post` / 404 `resource.not_found` |
| POST | `/posts/{id}/views` | - | | `204` |
| GET | `/blogs` | - | `page, page_size` | 목록 + `Blog[]` |
| GET | `/bookmarks` | 필수 | `page, page_size` | 목록 + `Post[]`(`is_bookmarked: true`) |
| POST | `/bookmarks` | 필수 | `{post_id}` | `201 {post_id, created_at}` / 404 / 409 |
| DELETE | `/bookmarks/{post_id}` | 필수 | | `204` / 404 |
| GET | `/filters/categories` | - | `blog_id, tags[]` | `{items,total}` |
| GET | `/filters/tags` | - | `blog_id, categories[]` | `{items,total}` |
| GET | `/filters/blogs` | - | `categories[], tags[]` | `{items,total}` |
| GET | `/trends/rising` | - | `period, limit` | 2.7 |
| GET | `/trends/series` | - | `tags[], period, interval` | 2.7 |
| GET | `/trends/posts` | - | `tags[], period, page, page_size` | 목록 + `Post[]` |

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
| GET | `/chat/sessions/{id}` | | `ChatSession`(messages 포함) / 404 |
| DELETE | `/chat/sessions/{id}` | | `204` |
| POST | `/chat/messages` | `{query, session_id?}` | `200 ChatAnswer` |
| POST | `/chat/messages/stream` | `{query, session_id?}` | SSE (§4) |

처리 순서: 프롬프트 가드 → 세션 검증 → 크레딧 1 차감 → 에이전트 → 성공 시 메시지 저장 / 실패 시 환불.
에러: `policy.blocked`(403) · `chat.session_not_found`(400) · `credit.insufficient`(402) · `llm.rate_limited`(429) · `llm.unavailable`(503).

### 3.4 어드민 (`role=admin`)
| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | `/admin/posts` | `page, page_size, summarized?, embedded?, blog_id?, q?` | 목록 + `AdminPost[]` |
| POST | `/admin/posts` | `{blog_id, title, link}` | `201 AdminPost` / 409 |
| DELETE | `/admin/posts/{id}` | | `204` |
| POST | `/admin/posts/{id}/summarize` | | `202 {job_id}` |
| POST | `/admin/posts/{id}/embed` | | `202 {job_id}` |
| GET | `/admin/blogs` | `page, page_size, is_active?` | 목록 + `AdminBlog[]` |
| POST | `/admin/blogs` | `{name,url,rss_url,blog_type,is_active}` | `201 AdminBlog` / 409 `details.field` |
| PUT | `/admin/blogs/{id}` | 동일 | `200 AdminBlog` |
| DELETE | `/admin/blogs/{id}` | `delete_posts=bool` | `200 {deleted_posts: n}` |
| POST | `/admin/blogs/{id}/activate` | | `200 AdminBlog`(자동 비활성화 해제) |
| GET | `/admin/users` | `page, page_size` | 목록 + `{user_code,email,name,role,credits:{remaining},created_at,updated_at}` |
| POST | `/admin/users/{user_code}/credits` | `{amount, expires_at}` | `201 {user_code, amount, expires_at}` |
| GET | `/admin/suggested-questions` | `page, page_size, include_inactive` | 목록 |
| POST | `/admin/suggested-questions` | `{text, sort_order, is_active}` | `201` / 409 `details.field="text"` |
| PUT | `/admin/suggested-questions/{id}` | 동일 | `200` |
| DELETE | `/admin/suggested-questions/{id}` | | `204` |
| GET | `/admin/jobs` | `status?`(pending\|running\|done\|dead), `type?, page, page_size` | 목록 + `Job[]` |
| GET | `/admin/jobs/stats` | | `{by_status:{pending,running,done,dead}, by_type:{…}, oldest_pending_at}` |
| POST | `/admin/jobs/{id}/retry` | | `200 Job`(status→pending, attempt→0) |
| POST | `/admin/jobs/retry-bulk` | `{type?, error_kind?, limit}` | `200 {retried: n}` |
| DELETE | `/admin/jobs/{id}` | | `204` |
| GET | `/admin/llm-models` | `purpose?` | 목록 + `LlmModelStat[]` |
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

프론트 `/admin`에 두 탭이 있다.
1. **운영(Ops)**: 잡 큐 상태 카드(pending/running/dead), 타입별 분포, 가장 오래된 pending, 실패 잡 목록(사유·attempt·재시도 버튼), 일괄 재시도, 백필 트리거.
2. **모델(LLM)**: 모델별 성공률·JSON 실패·429·평균 지연·scouter 헬스 표.
