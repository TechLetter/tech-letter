# Tech-Letter RAG 기반 챗봇 서비스 설계

## 1. 개요

Tech-Letter는 RSS 기반 기술 블로그 수집 → HTML 렌더링/파싱 → 요약까지의 파이프라인을 이미 가지고 있다.
이 설계서는 여기에 **RAG(Retrieval-Augmented Generation)** 기반 챗봇 서비스를 추가하여, 사용자가 자연어로 Tech-Letter 콘텐츠를 질의하고 대화할 수 있도록 하는 방식을 정의한다.

### 1.1 목표

- Tech-Letter에 수집/요약된 포스트들을 기반으로 **질문-답변(Question Answering)** 기능 제공
- 최신 포스트까지 반영된 **도메인 특화 Q&A 챗봇** 제공 (예: "최근 Go 성능 관련 글 요약해줘")
- 기존 이벤트 기반(aggregate → processor) 아키텍처 및 **eventbus 패턴**과 자연스럽게 통합
- 추후 확장이 가능하도록 **마이크로서비스 + Clean Architecture + SOLID 원칙**을 유지

### 1.2 범위

- 신규 **챗봇 API 서비스** 설계
- 신규 **임베딩/인덱싱 워커** 설계
- **벡터 스토어** 선택 및 데이터 모델 개략 정의
- **인덱싱 파이프라인 + 쿼리 파이프라인** 설계
- 배포/운영 전략 및 단계적 도입 계획

프론트엔드(웹 UI)는 최소 범위에서만 언급하며, 본 설계의 초점은 백엔드/인프라이다.

---

## 2. 요구사항

### 2.1 기능 요구사항

1. **포스트 기반 Q&A**

   - 질문에 대해 관련 포스트(제목/요약/본문 일부)를 검색 후, LLM이 근거를 바탕으로 답변한다.
   - 답변에는 **참고한 포스트 메타데이터(제목, URL, 발행일 등)** 를 함께 반환한다.

2. **Stateless 챗봇 API**

   - 모바일/멀티 클라이언트 환경을 고려하여 서버는 세션/대화 상태를 저장하지 않는다.
   - 각 요청은 독립적으로 처리되며, 필요한 경우 클라이언트가 과거 대화 내용을 함께 전송하는 방식으로 확장 가능하다.

3. **필터 기반 검색** (2차 단계)

   - 태그, 블로그 도메인, 발행일 범위 등을 기준으로 검색 범위를 제한하는 옵션.

4. **운영용 진단 기능**

   - 특정 포스트 ID/URL로 해당 포스트의 임베딩/인덱싱 상태 조회.
   - 특정 기간/전체 재인덱싱 트리거(관리자 기능).

5. **멀티 LLM/프로바이더 및 영역별 설정**
   - Gemini, OpenAI, Ollama 등 다양한 provider와 모델을 지원한다.
   - embedding, retrieval, chat 영역별로 provider/model/API key를 분리 설정할 수 있다.
   - 단, 동일 벡터 공간을 사용하기 위해 embedding과 retrieval은 동일 provider/model 조합을 사용해야 한다.

### 2.2 비기능 요구사항

1. **지연 시간**

   - 챗봇 답변: P95 기준 **3초 이하** (네트워크/LLM 호출 포함) 목표.
   - 장애 시에도 최대 5초 이내 타임아웃 및 명시적인 에러 응답.

2. **가용성 및 확장성**

   - 챗봇 API, 임베딩 워커, 벡터 스토어는 각각 독립적으로 수평 확장 가능해야 한다.

3. **일관된 에러 처리 및 로깅**

   - 공통 에러 응답 포맷 유지 (code, message, detail 필드 등).
   - 외부 시스템(LLM, 벡터 DB) 호출 실패 시 **명시적인 에러 로그 + 지표** 수집.

4. **구성 관리**
   - LLM provider/model/API 키, 벡터 스토어 주소, 토픽/컬렉션 이름 등은 모두 `config.yaml` / `application.yml` / 환경변수로 분리.
   - embedding, retrieval, chat 각 영역별 설정을 분리하되, embedding과 retrieval은 동일 모델 조합을 사용하도록 검증/제약을 둔다.

---

## 3. 전체 아키텍처

### 3.1 현재 아키텍처 요약

- **API 서버 (`cmd/api`)**: REST API (Gin), MongoDB 읽기/쓰기
- **Aggregate 서버 (`cmd/aggregate`)**: RSS 피드 수집, `PostCreated` 이벤트 발행
- **Processor 서버 (`cmd/processor`)**: 렌더링/파싱/요약 처리, 후속 이벤트 발행
- **메시지 브로커**: Kafka 기반, 신규 기능은 `eventbus` 패키지의 `KafkaEventBus` 사용 권장
- **DB**: MongoDB (포스트/요약/메타데이터 저장)

### 3.2 RAG 챗봇 추가 컴포넌트

1. **Chatbot API 서비스 (`cmd/chatbot`)**

   - 책임: 사용자 챗 요청 수신, RAG 파이프라인 실행, 응답 반환
   - 레이어 구조:
     - `handlers/`: HTTP 핸들러 (REST 엔드포인트)
     - `services/`: RAG 비즈니스 로직 (쿼리 임베딩 → 검색 → 프롬프트 구성 → LLM 호출)
     - `repositories/` or `adapters/`: 벡터 스토어 클라이언트, Mongo 리드 전용 리포지토리
     - `dto/`: Request/Response 정의

2. **Embedding/Indexing 워커 (`cmd/embedder` 또는 `cmd/rag_indexer`)**

   - 책임: 새로운/갱신된 포스트를 벡터 스토어에 인덱싱
   - eventbus Consumer로 동작
   - 요약 완료 이벤트(예: `PostSummarized`)를 구독하고 임베딩 생성 후 upsert

3. **벡터 스토어(Vector Store)**

   - 후보: Qdrant, Weaviate, pgvector, MongoDB Atlas Vector Search 등
   - 설계상은 **"Vector Store" 인터페이스**만 정의하고, 초기 구현으로 1개 선택 (예: Qdrant).
   - Docker Compose에 신규 컨테이너로 추가.

4. **LLM/Embedding 클라이언트**

   - RAG 전용으로 Gemini, OpenAI, Ollama 등 다양한 provider를 지원하는 추상 `LLMClient` / `EmbeddingClient` 계층을 둔다.
   - embedding, retrieval, chat 각각에 대해 provider/model/API 키를 설정으로 주입한다. (retrieval은 embedding과 동일 모델을 사용).
   - 기존 `summarizer`의 Gemini 사용 코드는 점진적으로 이 공용 클라이언트로 통합 가능하다.

### 3.3 상호 작용 개요

- Aggregate / Processor 파이프라인은 기존과 동일하게 동작.
- Processor에서 요약이 완료되면, `PostSummarized` (또는 RAG 전용 `PostReadyForIndex`) 이벤트를 **eventbus**로 발행.
- Embedding 워커가 해당 이벤트를 구독 → 벡터 인덱싱.
- 사용자가 Chatbot API에 질문 → 쿼리 임베딩 → 벡터 검색 → LLM 호출 → 답변 반환.

---

## 4. 데이터 파이프라인 설계

### 4.1 인덱싱 파이프라인 (오프라인/비동기)

1. **이벤트 발행 (Processor)**

   - 입력: RSS 수집 및 처리 후 MongoDB에 저장된 포스트 + 요약 데이터
   - 처리 완료 시 eventbus를 통해 `PostSummarized` 이벤트 발행
     - payload: `postId`, `title`, `summary`, `url`, `tags`, `publishedAt`, `language` 등

2. **Embedding 워커 (Consumer)**

   - eventbus Consumer 그룹: `tech-letter-rag-indexer`
   - 단계:
     1. 이벤트 역직렬화 및 유효성 검증
     2. 인덱싱 대상 텍스트 구성
        - 제목 + 요약 + (선택) 본문 일부 + 태그
     3. 텍스트 해시 및 임베딩 캐시 키 생성
        - 키 예시: `{provider}:{model}:{text_hash}`.
     4. 임베딩 캐시 조회
        - 캐시 히트 시, 저장된 벡터를 사용하고 Embedding API 호출을 생략한다.
     5. 캐시 미스 시 Embedding API 호출
        - 설정된 provider/model(예: Gemini, OpenAI, Ollama)을 사용하여 임베딩을 생성한다.
        - 실패 시 재시도 (eventbus retry 토픽 / DLQ 활용).
        - 성공 시 임베딩 캐시에 저장한다.
     6. 벡터 스토어에 upsert
        - `id = postId`
        - 메타데이터: 제목, URL, 태그, 발행일, 언어 등

3. **재인덱싱/백필**
   - 관리용 엔드포인트 or CLI를 통해 MongoDB의 기존 포스트를 스캔하며 순차 인덱싱
   - 대량 재인덱싱 시 배치 크기/지연을 두어 LLM API 및 벡터 스토어에 부담을 줄인다.

### 4.2 쿼리 파이프라인 (온라인/실시간)

1. **챗 요청 수신 (Chatbot API)**

   - 입력: `question`, 선택적 `filters`(태그, 기간 등), `topK`.
   - 서버는 세션/대화 상태를 저장하지 않으며, 각 요청은 독립적으로 처리된다.

2. **쿼리 임베딩 생성**

   - `question`에 대해 텍스트 해시 및 임베딩 캐시 키를 생성한다.
   - 임베딩 캐시에서 벡터를 조회하고, 캐시 미스 시 Embedding API를 호출하여 임베딩을 생성한다.
   - 실패 시 명시적인 에러 응답 + 로그/메트릭 기록.

3. **벡터 검색**

   - 상위 K개(예: 5~10개) 후보 포스트 검색
   - 후보에 대해 최소 메타데이터 + 필요 시 MongoDB에서 상세 조회

4. **프롬프트 구성 및 LLM 호출**

   - 후보 포스트들의 요약/본문 일부를 컨텍스트로 묶어서 시스템 프롬프트에 포함
   - LLM 호출 시 타임아웃/재시도 전략 명시 (config 기반)

5. **응답 조립 및 반환**
   - LLM 응답 텍스트 + 사용된 포스트 메타데이터 리스트를 Response로 반환
   - 필요 시 스트리밍 응답(추가 단계) 고려

---

## 5. 서비스 설계 (Clean Architecture 관점)

### 5.1 Chatbot API 서비스 (`cmd/chatbot`)

- **핸들러 레이어 (`handlers/`)**

  - HTTP 요청 파싱, 유효성 검사, DTO 변환
  - `ChatService` 인터페이스 호출

- **서비스 레이어 (`services/`)**

  - 핵심 책임: RAG 쿼리 파이프라인 조합
  - 의존성:
    - `EmbeddingClient`
    - `EmbeddingCacheRepository`
    - `VectorStoreClient`
    - `PostReadRepository` (Mongo 읽기)
    - `LLMClient`
    - `PromptBuilder`

- **리포지토리/어댑터 레이어 (`repositories/` or `adapters/`)**
  - MongoDB, 벡터 스토어, 외부 API에 대한 구체 구현
  - 인터페이스 기반으로 추상화하여 테스트 용이성 확보

### 5.2 Embedding/Indexing 워커 (`cmd/rag_indexer`)

- **이벤트 핸들러**

  - eventbus Consumer → `PostSummarized` 이벤트 → `IndexingService` 호출

- **IndexingService**

  - 입력: 포스트 메타데이터 + 텍스트
  - 책임:
    - 임베딩 요청 파라미터 구성
    - Embedding API 호출 및 에러 처리
    - VectorStore upsert

- **에러/재시도 전략**
  - eventbus의 delay-topics, DLQ를 활용한 재시도 설계
  - 반복 실패 시 DLQ로 보내고 알림/모니터링 연동

### 5.3 공통 모듈

- `llm` 패키지: Gemini, OpenAI, Ollama 등 provider를 추상화한 Chat/Embedding 클라이언트. provider/model/API 키를 영역별로 주입할 수 있고, 타임아웃/재시도/로깅을 내장한다.
- `vectorstore` 패키지: VectorStore 인터페이스 + Qdrant 등 구현체
- `rag` 패키지: Prompt 템플릿, RAG 유틸리티(컨텍스트 병합, 스코어링 등)
- `embeddingcache` 패키지: (provider, model, text_hash)를 키로 임베딩을 조회/저장하는 인터페이스와 구현체. 내부 저장소는 MongoDB/Redis 등으로 교체 가능하도록 추상화.

---

## 6. API 설계 (초안)

### 6.1 챗봇 질의 API

- **Endpoint**: `POST /v1/chat` (별도 `cmd/chatbot` 서비스 기준)
- **Request (예시)**

```json
{
  "question": "Go 성능 최적화 관련 최근 글 알려줘",
  "filters": {
    "tags": ["go", "performance"],
    "publishedAfter": "2024-01-01"
  },
  "topK": 5
}
```

- **Response (예시)**

```json
{
  "answer": "...LLM 생성 답변...",
  "references": [
    {
      "postId": "...",
      "title": "...",
      "url": "https://...",
      "publishedAt": "2024-01-23T00:00:00Z",
      "score": 0.82
    }
  ],
  "usage": {
    "promptTokens": 123,
    "completionTokens": 456
  }
}
```

### 6.2 공통 에러 응답 포맷 (예시)

```json
{
  "code": "VECTOR_STORE_UNAVAILABLE",
  "message": "벡터 스토어에 연결할 수 없습니다.",
  "detail": "qdrant: connection timeout"
}
```

- 모든 에러는 의미 있는 `code`와 사람이 읽을 수 있는 `message`를 제공.

---

## 7. 인프라 및 배포

### 7.1 Docker Compose 확장

- 신규 서비스 컨테이너
  - `techletter_chatbot`: `cmd/chatbot` 바이너리
  - `techletter_rag_indexer`: `cmd/rag_indexer` 바이너리
- 신규 인프라 컨테이너
  - `vector_store`: Qdrant (또는 선택된 벡터 DB)

### 7.2 설정값 및 시크릿

- 공통: `config-{env}.yaml` 또는 환경변수로 분리
  - `RAG_ENABLED`
  - `VECTOR_STORE_URL`
  - `VECTOR_STORE_COLLECTION_NAME`
  - `RAG_EMBEDDING_PROVIDER`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_API_KEY` (embedding 및 retrieval용)
  - `RAG_CHAT_PROVIDER`, `RAG_CHAT_MODEL`, `RAG_CHAT_API_KEY` (대화용)
  - `EMBEDDING_CACHE_BACKEND` (mongo, redis 등), `EMBEDDING_CACHE_TTL`
  - `RAG_MAX_CONTEXT_DOCS`
  - eventbus용 토픽 이름, 그룹 ID 등

### 7.3 모니터링/로깅

- 메트릭 예시
  - 쿼리 지연 시간(P50/P95)
  - LLM 호출 실패율
  - 벡터 검색 실패율
  - 인덱싱 처리량, 실패/재시도 건수
- 로그
  - 에러/워닝은 반드시 컨텍스트(요청 ID, 포스트 ID 등) 포함

---

## 8. 단계별 도입 계획

### 8.1 1단계: 인프라 & 골격 구축

- 벡터 스토어 선택 및 Docker Compose에 추가
- `vectorstore` / `llm` 공용 패키지 초안 구현
- `cmd/chatbot`, `cmd/rag_indexer` 서비스 스켈레톤 생성 (핸들러/서비스/리포지토리 인터페이스만 정의)

### 8.2 2단계: 인덱싱 파이프라인 구현

- Processor에서 `PostSummarized` 이벤트 발행 경로 확정 (또는 신규 `PostReadyForIndex` 이벤트 정의)
- eventbus 기반 Embedding 워커 구현
- 기존 포스트에 대한 백필/재인덱싱 배치 구현

### 8.3 3단계: RAG 쿼리 파이프라인 & MVP 챗봇

- `POST /v1/chat` 엔드포인트 구현
- 기본 프롬프트 템플릿 설계 및 파라미터 튜닝
- 간단한 웹 UI 또는 API 클라이언트로 기능 검증

### 8.4 4단계: 고도화

- 필터링/랭킹 전략 개선 (예: 재랭킹 모델 도입 등)
- (필요 시) 대화 컨텍스트 관리 고도화 (클라이언트 제공 히스토리 요약/축약, 요청 단위 컨텍스트 관리)
- 품질 평가 파이프라인 구축 (테스트 질문 세트, 자동 평가 지표 등)

---

## 9. 리스크 및 고려사항

1. **LLM/Embedding 비용 및 한도**

   - 대량 인덱싱 및 잦은 쿼리에 따른 비용 관리 필요
   - 쿼리 캐싱, 토큰 길이 제한, 히스토리 길이 제한으로 제어

2. **검색 품질**

   - 임베딩 입력 텍스트 선택(제목/요약/본문/태그 조합)에 따라 품질 편차 발생
   - 실험을 통해 최적 조합 및 가중치 탐색 필요

3. **일관성 및 지연**

   - 포스트 생성/수정 → 요약 → 인덱싱까지의 지연 동안은 RAG에서 최신 내용이 반영되지 않을 수 있음
   - SLA 관점에서 허용 지연 시간을 정의하고 모니터링 필요

4. **아키텍처 복잡도 증가**

   - 신규 서비스/인프라 추가로 운영 복잡도 증가
   - 각 컴포넌트의 책임을 명확히 나누고, 헬스체크/대시보드 등으로 가시성을 확보해야 함.

5. **임베딩 캐시 저장소 선택 및 운영**

   - 임베딩 캐시를 어디에 저장할지(MongoDB, Redis, 별도 KV 스토어 등)에 따라 비용/운영 복잡도가 달라진다.
   - 캐시 크기/TTL 전략을 잘못 설계하면 메모리/스토리지 사용량이 급증하거나 캐시 효율이 떨어질 수 있다.
