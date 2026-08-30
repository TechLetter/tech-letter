# 데이터 모델 (MongoDB · Qdrant)

## 1. MongoDB (`techletter` DB, mongo:8.0)

### 1.1 컬렉션
| 컬렉션 | 담당 모듈 | 비고 |
|---|---|---|
| `posts` | `content` | 핵심 데이터 |
| `blogs` | `content` | |
| `users` | `users` | |
| `bookmarks` | `users` | |
| `credits` | `users` | TTL로 매일 소멸·재생성 |
| `credit_transactions` | `users` | |
| `identity_policies` | `users` | 일일 지급 중복 방지 |
| `login_sessions` | `users` | TTL 60초 |
| `chat_sessions` | `chat` | |
| `chat_suggested_questions` | `chat` | |
| `jobs` | `core.jobs` | 잡 큐. 상태 4종: pending/running/done/dead |
| `llm_model_stats` | `core.llm` | 모델×용도별 성적. `_id = "{model_id}:{purpose}"` |
| `llm_daily_usage` | `core.llm` | provider별 일일 사용량. `_id = "{date}:{provider}"`, TTL 30일 |

### 1.2 인덱스
```
blogs      uniq_rss_url {rss_url:1} UNIQUE · idx_blog_name {name:1} · idx_blog_is_active {is_active:1}
bookmarks  uniq_user_code_post_id {user_code:1,post_id:1} UNIQUE · idx_user_code_created_at_desc {user_code:1,created_at:-1}
credits    ttl_expired_at {expired_at:1} TTL=0 · idx_user_expired {user_code:1,expired_at:1}
identity_policies  idx_identity_policy_unique {identity_hash:1,policy_key:1} UNIQUE
login_sessions     uniq_login_session_id {session_id:1} UNIQUE · ttl_login_session_expires_at {expires_at:1} TTL=0
posts      idx_published_at_desc {published_at:-1} · idx_categories {aisummary.categories:1}
           idx_tags {aisummary.tags:1} · uniq_link {link:1} UNIQUE
           idx_published_at_id_desc {published_at:-1,_id:-1}
           idx_tags_published_at {aisummary.tags:1,published_at:-1}
           idx_categories_published_at {aisummary.categories:1,published_at:-1}
           idx_posts_summarized {status.ai_summarized:1}
users      uniq_user_code {user_code:1} UNIQUE · uniq_provider_provider_sub {provider:1,provider_sub:1} UNIQUE
chat_sessions            idx_chat_user_updated {user_code:1, updated_at:-1}
chat_suggested_questions uniq_suggested_normalized {normalized_text:1} UNIQUE
credit_transactions      idx_credit_tx_user_created {user_code:1, created_at:-1}
jobs       idx_jobs_claim {status:1,type:1,priority:1,run_at:1} · idx_jobs_stale {status:1,locked_at:1}
           idx_jobs_dedupe {key:1,type:1,status:1}
           ttl_jobs_done {finished_at:1} TTL 14일, partialFilterExpression {status:"done"}
```
인덱스는 부팅 시 `IndexRegistry`가 한 번 생성한다(요청마다 만들지 않는다).

### 1.3 문서 스키마

**`posts`** — 계약(API)에서 이름이 바뀌는 필드가 있지만 DB 필드명은 아래 그대로다.
```
_id, created_at, updated_at,
blog_id(ObjectId), blog_name, title, link(UNIQUE), published_at, thumbnail_url, view_count,
status: { ai_summarized: bool, embedded: bool, failed_reason: str|null },
aisummary: { categories[], tags[], summary, model_name, generated_at } | null,
plain_text: str|null,
embedding: { model_name, collection_name, vector_dimension, chunk_count, embedded_at } | 없음
```
API 계약에서는 `status.ai_summarized` → `status.summarized`, `aisummary` → `ai_summary`로 이름이 바뀐다(변환은 DTO 레벨에서만 일어난다).

**`blogs`**: `_id, created_at, updated_at, name, url, rss_url(UNIQUE), blog_type("company"|"creator"), is_active, tls_insecure, consecutive_failures, last_fetched_at, last_fetch_error`
- `last_fetch_error`는 200자 이내로 절단해서 저장한다.
- `consecutive_failures`가 임계치를 넘으면 RSS 수집기가 `is_active=false`로 자동 전환한다.

**`users`**: `_id, created_at, updated_at, user_code("google:<uuid>", UNIQUE), provider, provider_sub, email, name, profile_image, role("user"|"admin")`

**`bookmarks`**: `_id, user_code, post_id(문자열), created_at, updated_at`

**`credits`**: `_id, user_code, amount, original_amount, source("daily"|"event"|"admin"), reason, expired_at(TTL), created_at, updated_at`

**`credit_transactions`**: `_id, created_at, updated_at, user_code, credit_id, type("grant"|"consume"|"refund"|"admin_grant"), amount, reason, metadata`

**`identity_policies`**: `_id, identity_hash, policy_key("DAILY_CREDIT_GRANT"), last_acted_at, created_at, updated_at`

**`login_sessions`**: `_id, session_id(UNIQUE), jwt_token, expires_at(TTL 60s), created_at, updated_at`

**`chat_sessions`**: `_id, user_code, title, created_at, updated_at, messages[{role, content, created_at, metadata?}], memory?{summary, covered_message_count, status, requested_at, updated_at, error_message}`
- API 계약은 `metadata`를 평탄화해서 노출하지만 DB 구조는 그대로 중첩돼 있다.

**`chat_suggested_questions`**: `_id, created_at, updated_at, text, normalized_text, sort_order, is_active`

### 1.4 규약
- 모든 `*_at`은 BSON Date(UTC). Python 쪽은 aware UTC datetime만 쓴다(`core/time.utcnow()`). naive datetime 저장 금지.
- 외부 노출 `id`는 `str(ObjectId)`. `bookmarks.post_id`는 문자열로 저장하고, `posts.blog_id`는 ObjectId로 저장한다.
- 필드를 `null`로 지우는 갱신이 막히지 않도록 `exclude_none`을 무분별하게 쓰지 않는다.

## 2. Qdrant

| 항목 | 값 |
|---|---|
| 컬렉션 | `tech_letter_posts__gemini-embedding-001__3072` (규칙 `{base}__{model}__{dim}`) |
| 벡터 | 3072-dim, Cosine |
| payload | `post_id, title, blog_name, link, published_at, categories, tags, chunk_index, chunk_text, model_name` |
| on_disk_payload | true |

- point id는 `uuid5(NAMESPACE_URL, "{post_id}:{model}:{dim}:{chunk_index}")` — 결정적이므로 upsert가 멱등하다.
- 삭제는 `{base}__` 접두어를 가진 모든 컬렉션에서 `post_id`가 일치하는 포인트를 제거한다.
- 임베딩 모델은 Gemini `gemini-embedding-001`로 고정돼 있어 컬렉션명이 항상 같은 값으로 계산된다.

## 3. 환경변수 이름

| 변수 | 용도 |
|---|---|
| `MONGO_URI` | Mongo 접속 |
| `JWT_SECRET` | JWT HS256 — 바꾸면 전체 재로그인이 필요하다 |
| `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET` | OAuth |
| `SUMMARY_WORKER_LLM_API_KEY` | 요약 1순위(Gemini) |
| `EMBEDDING_WORKER_LLM_API_KEY` | 임베딩(Gemini) |
| `CHATBOT_LLM_API_KEY` | OpenRouter 키(요약 폴백·챗봇 공용) |
| `CHATBOT_EMBEDDING_API_KEY` | 쿼리 임베딩(Gemini) |
| `SCRAPERAPI_KEY` | 렌더러 대안 |

전체 목록은 `techletter settings example`로 생성한다(코드가 최신 출처).
