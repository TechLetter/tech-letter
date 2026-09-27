# 검색 (하이브리드 BM25 + 벡터) · 검색 AI 요약

코드: `src/techletter/search/`(`lexical.py` 토큰화·BM25, `service.py` 융합·순위, `handlers.py` 색인 잡), Qdrant 접근은 `core/db/qdrant.py`. 설정은 `SearchSettings`(env prefix `SEARCH_`).

## 1. 왜 두 가지를 섞나

- **어휘(BM25)**: "vllm", "카프카"처럼 단어가 그대로 들어간 글을 잘 찾는다. 벡터 검색은 이런 고유명사에 약하다.
- **벡터(dense)**: 표현이 달라도 뜻이 가까운 글을 찾는다. 대신 무엇을 물어도 무언가를 돌려준다 → 벡터로만 걸린 글은 점수가 높을 때만 남긴다.
- 두 점수는 척도가 달라 더하지 않고 **순위로 섞는다(RRF)**.

## 2. 어휘 색인 (`{base}__lexical`)

| 항목 | 값 |
|---|---|
| 컬렉션 | `tech_letter_posts__lexical` — 포스트당 포인트 1개, id `uuid5(…, "{post_id}:lexical")` |
| 벡터 | sparse `bm25`, `modifier=IDF`(IDF는 Qdrant가 질의 때 곱한다 → 문서가 늘어도 기존 포인트를 다시 계산하지 않는다) |
| payload | `post_id, blog_id, categories, published_at, title, blog_name, link` (자동완성은 Mongo를 거치지 않고 이 값을 그대로 쓴다) |
| payload index | `post_id`, `blog_id`, `categories` (keyword) |
| 삭제 | 벡터 청크와 같은 `{base}__` prefix라 `embedding.delete_requested`가 함께 지운다 |

**토큰화** (`tokenize`): NFKC 정규화·소문자화 후 라틴 문자(악센트 포함)·숫자 묶음과 한글 음절 묶음만 본다. 나머지 문자는 구분자다. 형태소 분석기를 들이지 않는다.
- 한글: **글자 2-gram**("카프카를" → 카프·프카·카를). 조사가 붙은 어절도 맞는다. 1·3글자 어절은 통째로도 넣는다("카카오").
- 라틴·숫자: 2글자 이상 단어 그대로("vllm", "k8s", "cdc").
- 토큰 → 차원 번호는 `crc32`(프로세스·버전이 달라도 같아야 해서 `hash()`를 쓰지 않는다).

**필드 가중치** (tf에 곱한다): `title 3.0` · `tags 2.0` · `categories 1.0` · `blog_name 1.0` · `summary 1.0`. 본문(`plain_text`)은 넣지 않는다 — 요약·제목 수준의 짧은 문서면 2-gram으로 충분하다.

**BM25**: `k1=1.2`, `b=0.75`, 문서 쪽 값 `tf·(k1+1) / (tf + k1·(1−b+b·dl/avgdl))`, 질의 쪽은 토큰마다 1.
- `AVG_DOC_LENGTH = 170`(가중치 곱한 토큰 수) — **상수다**. 문서가 들어올 때마다 평균을 다시 재면 먼저 넣은 문서와 기준이 어긋난다. 운영 요약(200자 안팎) 샘플로 잰 값이며, `techletter backfill lexical --dry-run`이 코퍼스 실측 평균을 보여 준다. 크게 벌어지면 상수를 고치고 `--execute`로 다시 백필한다.

**색인 시점** (`search.lexical_index_requested` 잡, embedding-worker가 처리):
- `summary.completed` 반영 직후 worker가 **임베딩 잡과 나란히** 건다. 원래는 임베딩 뒤에 걸었는데, 임베딩 쿼터가 며칠 밀린 동안 새 글 190건이 검색에 안 나왔다(2026-09-27) → 요약만 있으면 색인한다.
- `techletter backfill topics --execute`로 주제를 재분류한 글도 다시 건다(주제 필터가 옛 값으로 남지 않게).
- 요약되지 않은 글이면 건너뛴다(공개 검색은 요약된 글만 다룬다).
- 전체 재색인: `techletter backfill lexical --execute` — 잡을 거치지 않고 바로 upsert, Gemini를 부르지 않아 수 초면 끝난다. 포인트 id가 고정이라 여러 번 돌려도 덮어쓸 뿐이다.

## 3. 검색 흐름 (`GET /api/v1/posts?q=`)

```
q 정규화: 공백 정리, 2글자 미만이면 검색 안 함(일반 최신순 목록), 100자에서 자름
 ├─ 어휘: Qdrant sparse 검색 상위 100(SEARCH_LEXICAL_CANDIDATES), blog_id·주제 필터를 Qdrant에서 먼저 적용
 │        (주제와 태그가 함께 오면 합집합 필터라 주제로 미리 좁히지 않고 Mongo에 맡긴다)
 └─ 벡터: 질의 임베딩 → 청크 컬렉션 상위 100청크(SEARCH_DENSE_CANDIDATES) → 포스트별 최고 점수로 묶음
          어휘에도 걸린 글은 그대로, 벡터로만 걸린 글은 코사인 ≥ 0.7(SEARCH_DENSE_MIN_SCORE)만 남김
RRF: Σ 1/(60 + 순위)  (SEARCH_RRF_K=60, 동점이면 어휘 순서)
Mongo: 필터(주제·태그·블로그·기간)와 요약 여부를 최종 판정, published_at 조회
최신성: 점수 × max(0.5, 0.5^(경과일/1100))  → 1년 ≈0.8배, 2년 ≈0.65배, 하한 0.5
상위 100건(SEARCH_MAX_RESULTS)까지 → 페이지로 잘라 Post 카드 반환 (total ≤ 100)
```
- 벡터 쪽 하한 0.7은 챗봇 RAG의 `CHATBOT_RAG_SCORE_THRESHOLD`(0.5)보다 높다 — 그건 답변 문맥용이라 목록에는 느슨하다.
- 최신성 하한 0.5: 오래됐어도 훨씬 관련 깊은 글은 위에 남게.
- 응답 모양·필터·페이지는 일반 목록과 같다. 그래서 별도 `/search` 대신 `/posts?q=`를 쓴다.

**장애·한도 시 낮춤** (검색 전체가 막히지 않게):
- 어휘 검색 실패 → 벡터만. 벡터(임베딩 한도·Qdrant) 실패 → 어휘만. 색인 컬렉션이 없는 새 환경 → 빈 결과.
- **질의 벡터 캐시**: 프로세스 메모리 LRU 256개·TTL 1시간(`SEARCH_QUERY_CACHE_SIZE/_TTL_SECONDS`). 같은 검색어로 페이지를 넘길 때 임베딩을 다시 부르지 않는다.
- **IP당 임베딩 한도**: 분당 30회(`SEARCH_EMBEDS_PER_MINUTE_PER_CLIENT`, 0이면 끔). 넘으면 벡터를 건너뛰고 어휘 결과만 준다. 검색 임베딩은 챗봇·임베딩 워커와 같은 Gemini 분당·일일 한도를 쓰기 때문이다. 캐시 적중은 세지 않는다. IP는 `X-Forwarded-For`의 **마지막** 값(Traefik이 본 실제 주소, 앞쪽 값은 클라이언트가 위조 가능). api 프로세스 메모리에만 있어 프로세스가 늘면 한도도 늘어난다.

## 4. 자동완성 (`GET /api/v1/search/suggest?q=`)

어휘 검색만 쓴다(글자를 칠 때마다 임베딩을 부르면 분당 한도를 금방 넘는다). 상위 5개(`SEARCH_SUGGEST_LIMIT`), 표시값은 색인 payload에서 바로 쓰고 **지금도 요약된 글인지만** Mongo에 확인한다(삭제 잡이 밀렸거나 요약이 되돌려진 글이 남지 않게). 실패하면 빈 목록.

## 5. 검색 결과 AI 요약 (`POST /search/summary`)

검색 결과 위의 "AI 요약"은 전용 API다(`search/summary.py::SearchSummaryService`). 로그인 사용자에게 **크레딧 없이** 준다. 프론트는 결과가 뜨면 바로 부른다(버튼·재시도 없음).

- 입력: `{query, post_ids}`. `post_ids`는 검색 결과 순서 그대로 최대 8개(ObjectId만, 중복 제거).
- **캐시 7일**: 키는 `sha256(소문자·공백 정리한 검색어 + 앞 5개 post_id)`이다. `search_summaries` 컬렉션에 저장하고 `created_at` TTL로 지운다. 사용자 식별자는 저장하지 않는다. 근거 글이 없거나 출력 가드에 막힌 답은 저장하지 않는다.
- **호출 제한**: 캐시에 없는 요청만 사용자별 분당 6회(`MISSES_PER_MINUTE`, API 프로세스 메모리). 넘으면 429 `llm.rate_limited`. 무료 모델의 하루 한도를 요약 워커의 폴백·모델 헬스체크와 함께 쓰기 때문이다.
- 같은 키를 동시에 요청하면 하나만 만든다(진행 중 태스크 공유). 요청이 끊겨도 끝까지 만들어 저장한다.
- 입력 가드(`PromptGuard`)는 검색어에 그대로 적용한다. 챗봇 세션은 만들지 않는다.
- **"이어서 묻기"**: `POST /search/summary/continue {key}` → 그 질문(user)과 답(assistant, 출처 포함)을 담은 챗봇 세션을 만들고 `{session_id}`를 준다. 캐시가 만료됐으면 404.
- 에이전트는 챗봇과 같은 `ChatAgent`(`Container.chat_agent`)의 `post_ids` 경로다. 채팅 API는 더 이상 `post_ids`를 받지 않는다.

| | 검색 AI 요약 | 챗봇 |
|---|---|---|
| 계획 | 플래너 없이 `answer_from_posts`, `strict_scope`, `brief=True`, `reason=search_summary` | 플래너가 정함 |
| 근거 | 앞 **5개** 글(`BRIEF_MAX_POSTS`)의 **요약본만**(요약 없는 글은 뺀다) | 플래너가 고른 도구의 결과(포스트 본문·벡터 청크) |
| 프롬프트 | `BRIEF_ANSWER_SYSTEM_PROMPT`: 굵은 핵심 한 문장 + 불릿 ≤3개, 불릿마다 `[n]` 출처 번호, 전체 320자 미만 | `ANSWER_SYSTEM_PROMPT`: 2~3문장 직답 → `###` 소제목으로 배경·블로그별 접근·수치·트레이드오프·비교, 보통 600~1500자 |

- 요약본만 쓰는 이유: 짧게 답하는데 본문 여러 편을 넣으면 컨텍스트 상한에 걸려 뒤쪽 글이 잘린다. 요약 5개 전부가 낫다.
- `[n]`은 `post_ids` 순서(= 검색 순위)를 따른다. 출처(`sources`)에 `blog_id`·`published_at`이 실려 프론트가 아이콘·날짜를 그린다.
- 두 프롬프트 첫 줄은 출력 누출 차단 목록(`chat/guards/rules.py::OUTPUT_LEAK_PHRASES`)에 있다. 프롬프트를 고치면 이 목록도 맞춘다.

## 6. 운영 메모

- 새 글이 검색에 안 나온다 → `techletter jobs list --status pending`에서 `search.lexical_index_requested` 적체 확인(embedding-worker가 처리한다), 급하면 `techletter backfill lexical --execute`.
- 순위 조정은 코드 배포 없이 `SEARCH_*` env로 가능하지만 compose가 주입하지 않으므로 `docker/compose.prod.yml`에 추가해야 한다. 가중치·`AVG_DOC_LENGTH`는 코드 상수이며 바꾸면 재백필이 필요하다.
- 테스트: `tests/unit/search/`(토큰화·RRF·최신성·캐시·한도), `tests/integration/test_search.py`, `tests/contract/test_search_contract.py`.
