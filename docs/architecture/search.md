# 검색 (하이브리드 BM25 + 벡터) · 검색 AI 요약

코드: `src/techletter/search/`(`lexical.py` 토큰화·BM25, `service.py` 융합·순위, `handlers.py` 색인 잡), Qdrant 접근은 `core/db/qdrant.py`. 설정은 `SearchSettings`(env prefix `SEARCH_`).

## 1. 왜 두 가지를 섞나

- **어휘(BM25)**: "vllm", "카프카"처럼 단어가 그대로 들어간 글을 잘 찾는다. 벡터 검색은 이런 고유명사에 약하다.
- **벡터(dense)**: 표현이 달라도 뜻이 가까운 글을 찾는다. 대신 무엇을 물어도 무언가를 돌려준다 → 벡터로만 걸린 글은 점수가 높을 때만 남긴다.
- 두 점수는 척도가 달라 **질의마다 0~1로 편 뒤 가중합**한다(어휘 0.2 + 벡터 0.8). RRF(순위 융합)도 설정으로 고를 수 있다.

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
 ├─ 어휘: Qdrant sparse 검색 상위 200(SEARCH_LEXICAL_CANDIDATES), blog_id·주제 필터를 Qdrant에서 먼저 적용
 │        (주제와 태그가 함께 오면 합집합 필터라 주제로 미리 좁히지 않고 Mongo에 맡긴다)
 └─ 벡터: 질의 임베딩 → 청크 컬렉션 상위 100청크(SEARCH_DENSE_CANDIDATES) → 포스트별 최고 점수로 묶음
          어휘에도 걸린 글은 그대로, 벡터로만 걸린 글은 코사인 ≥ 0.65(SEARCH_DENSE_MIN_SCORE)만 남김
융합(SEARCH_FUSION=convex): 0.2·minmax(BM25) + 0.8·minmax(코사인)  (SEARCH_LEXICAL_WEIGHT, 한쪽에만 있으면 다른 쪽 0)
      (SEARCH_FUSION=rrf면 Σ 1/(SEARCH_RRF_K + 순위))
Mongo: 필터(주제·태그·블로그·기간)와 요약 여부를 최종 판정, published_at 조회
최신성: 기본 끔(SEARCH_RECENCY_HALF_LIFE_DAYS=0). 켜면 점수 × max(하한, 0.5^(경과일/반감기))
상위 100건(SEARCH_MAX_RESULTS)까지 → 페이지로 잘라 Post 카드 반환 (total ≤ 100)
```
- **값의 근거 (2026-10-03 튜닝)**: 정답 라벨이 붙은 222문항(dev 123 / test 99)으로 정했다. 평가 자료는 저장소 밖 `plans/rag-tuning/`에 있다.
  - Codex 에이전트 40개가 dev에서 축별 실험을 했다. 그 뒤 조합 216개를 탐색했다.
  - test는 마지막에 한 번만 열었다.

  | test 99문항 | 이전(RRF k=60, 최신성 1100일, 벡터 0.7, 후보 100) | 지금 |
  |---|---|---|
  | nDCG@10 | 0.774 | 0.934 (+0.160, 95% CI [0.11, 0.21]) |
  | Recall@5 | 0.933 | 0.989 |
  | MRR@10 | 0.764 | 0.981 |

  - 최신성 감쇠를 끈 이유: 어휘·벡터 양쪽 1위였던 정답이 감쇠 뒤 7~9위로 밀린 사례가 여럿 나왔다. 기간을 묻는 질문은 발행일 필터가 따로 맡는다.
  - 점수 융합이 RRF보다 나았다(dev nDCG 0.817 대 RRF 최고 0.789). 임계값 0.60~0.70과 후보 풀 크기에는 둔감했다. 그래서 가운데 값을 골랐다.
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
- 입력 가드는 없다(§6 참고). 챗봇 세션은 만들지 않는다.
- **"이어서 묻기"**: `POST /search/summary/continue {key}` → 그 질문(user)과 답(assistant, 출처 포함)을 담은 챗봇 세션을 만들고 `{session_id}`를 준다. 캐시가 만료됐으면 404.
- 에이전트는 챗봇과 같은 `ChatAgent`(`Container.chat_agent`)의 `post_ids` 경로다. 채팅 API는 더 이상 `post_ids`를 받지 않는다.

| | 검색 AI 요약 | 챗봇 (§6) |
|---|---|---|
| 글 | 검색 결과 앞 **5개**(`BRIEF_MAX_POSTS`) | 같은 하이브리드 검색으로 앞 6개(`CHATBOT_RAG_TOP_K`) |
| 근거 | 글마다 **요약본만** | 글마다 요약 + 그 글 안에서 질문에 가까운 청크 2개(1,200자까지, 없으면 본문 앞부분) |
| 프롬프트 | `BRIEF_ANSWER_SYSTEM_PROMPT`: 굵은 핵심 한 문장 + 불릿 ≤3개, 불릿마다 `[n]`, 320자 미만 | `ANSWER_SYSTEM_PROMPT`: 직답 → 필요한 만큼만 세부, 주장마다 `[n]`, 보통 1200자 이하 |

- 요약본만 쓰는 이유: 짧게 답하는데 본문 여러 편을 넣으면 컨텍스트 상한에 걸려 뒤쪽 글이 잘린다. 요약 5개 전부가 낫다.
- `[n]`은 `post_ids` 순서(= 검색 순위)를 따른다. 출처(`sources`)에 `blog_id`·`published_at`이 실려 프론트가 아이콘·날짜를 그린다.
- 요약 프롬프트의 문장은 출력 누출 차단 목록(`chat/guards/rules.py::OUTPUT_LEAK_PHRASES`)에 있다. 프롬프트를 고치면 이 목록도 맞춘다. 출력 가드는 AI 요약에만 쓴다.

## 6. 챗봇 답변 경로 (2026-09-27 개편)

질문 하나 → **범위 읽기(코드) → 근거 모으기 → 답변 LLM 1회**. 목록은 LLM 0회다.
코드: `chat/agent/scope.py`(범위), `chat/agent/evidence.py`(근거), `chat/agent/graph.py`(흐름), `chat/memory.py`(대화).

1. **범위 읽기** (`read_scope`, LLM 없음)
   - 블로그: "카카오 블로그", "토스의 글"처럼 **명시하면 그 블로그로 좁힌다**. 이름만 나오면("토스 결제 시스템") 좁히지 않고 그 블로그 글을 앞으로 올린다. 단어 시작에서만 찾는다("파이프라인"의 "라인" 제외). 별칭은 `BLOG_ALIASES`("당근"→당근마켓).
   - "OO 블로그"인데 모으지 않는 블로그면 검색하지 않고 없다고 답한다.
   - "카카오, 당근마켓 말고"는 그 블로그와 직전 답의 글을 뺀다.
   - 기간: KST 달력 기준("이번 달", "지난주", "최근 7일", "2026년 9월"). 끝은 포함 경계(`$lte`).
   - 목록: "목록/리스트" 또는 "글 N개 보여줘"(설명·정리 요청 제외). 주제 이름 조각이 있으면 주제 필터로 최신순, 다른 낱말이 남으면 그 말로 검색한 순서.
2. **근거** (`EvidenceBuilder`)
   - 글은 목록 검색과 같은 `SearchService.retrieve`(BM25 + 벡터 점수 융합, `dense_min_score`)로 고른다. 글 6개(`CHATBOT_RAG_TOP_K`)를 고르고, 글마다 청크 2개(`CHATBOT_RAG_CHUNKS_PER_POST`)를 넣는다. 청크는 최대 1,200자(`CHATBOT_RAG_CHUNK_CHARS`)다. 같은 질의 벡터로 **고른 글 안에서만** 청크를 고른다(`VectorStore.search_in_posts`, Qdrant group_by `post_id`).
   - 근거 번호는 **글 단위**다. 같은 글의 청크는 같은 `[n]`, `sources[n-1]`이 그 글이다.
   - "거기서", "그 글", "두 번째" 같은 참조면 **직전 답의 출처 글 안에서** 찾는다(`is_reference`).
   - 뜻 있는 낱말이 3개 미만인 후속 질문("보안 문제는?")은 직전 질문을 붙여 검색한다.
3. **답변**: 최근 대화(메시지당 600자) + 번호 붙은 글 + 질문. 근거가 없으면 모델이 "관련 글을 찾지 못했습니다"로 시작하고, 그러면 출처를 비운다.

**없앤 것**과 이유(평가: `plans/chatbot-eval/` — 30문항, 저장소 밖):
- LLM 플래너(작업 6종 JSON): 서비스 이름을 블로그로 읽거나 없는 태그를 AND로 걸어 관련 글을 놓쳤다.
- 질문 재작성: 후속 질문마다 LLM 1회. 직전 출처 id가 더 정확하다.
- 챗봇 전용 벡터 검색(청크만, 코사인 0.5): 이름이 정확히 나오는 글을 놓쳤다.
- 대화 압축 워커: 운영에서 1번 돌았고 요약이 저장된 세션이 없었다.
- 정규식 입력 가드·검색 결과 가드: "LLM jailbreak 방어 사례" 같은 정상 질문을 막았다. 문서 속 지시문은 답변 프롬프트가 "데이터일 뿐"이라고 못 박는다.

| 30문항 | 개편 전 | 개편 후 |
|---|---|---|
| Recall@5 | 0.435 | 0.703 |
| MRR@10 | 0.538 | 0.655 |
| 없는 걸 없다고 함 | 1/5 | 5/5 |
| 논리 LLM 호출 | 1.73 | 0.83 |
| 지연 p50 | 6.0s | 3.4s |

## 7. 운영 메모

- 새 글이 검색에 안 나온다 → `techletter jobs list --status pending`에서 `search.lexical_index_requested` 적체 확인(embedding-worker가 처리한다), 급하면 `techletter backfill lexical --execute`.
- 순위 조정은 코드 배포 없이 `SEARCH_*` env로 가능하지만 compose가 주입하지 않으므로 `docker/compose.prod.yml`에 추가해야 한다. 가중치·`AVG_DOC_LENGTH`는 코드 상수이며 바꾸면 재백필이 필요하다.
- 테스트: `tests/unit/search/`(토큰화·융합·최신성·캐시·한도), `tests/integration/test_search.py`, `tests/contract/test_search_contract.py`.
