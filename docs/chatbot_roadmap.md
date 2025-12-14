# 챗봇 기능 명세 및 로드맵

이 문서는 Tech-Letter 챗봇 기능의 **Phase 1(현재)** 범위와 구현 내용을 정리하고,
**Phase 2 / Phase 3**에서 진행할 작업 계획의 초석을 정의한다.

---

## 0. 목표

- **API Gateway(Go)** 를 단일 진입점으로 유지하면서, RAG 챗봇 기능을 외부 사용자에게 제공한다.
- 내부적으로는 **이벤트 기반 임베딩 파이프라인**(요약 → 임베딩 → Vector DB upsert)을 통해 검색 품질을 확보한다.

---

## 1. Phase 1 (MVP) 범위

### 1.1 제공 기능

- **RAG 챗봇 질의 API**
  - API Gateway: `POST /api/v1/chatbot/chat`
  - 내부 호출: `chatbot_service POST /api/v1/chat`
- **사용 조건**
  - Phase 1에서는 **로그인된 사용자(JWT 유효)** 인지만 확인한다.
  - 크레딧/쿼터/요금제는 Phase 2에서 도입한다.

### 1.2 응답 포맷 정책

- 현재 외부 공개 API에서 응답 포맷 강제는 아래만 적용한다.
  - `pagination`
  - `error` (`{"error": "..."}`)
  - `message` (`{"message": "..."}`)
- 챗봇 성공 응답은 **외부 공개 정책상 sources를 노출하지 않고** `answer`만 반환한다.

### 1.3 에러 코드 정책 (API Gateway)

- `401`: 로그인 필요/토큰 오류
- `400`: 요청 형식 오류
- `429`: AI API rate limit (일시적인 제한)
- `503`: 챗봇/AI 제공자 일시 장애
- `500`: 기타 서버 오류

모든 에러 응답은 Gateway 공통 규칙에 따라 `{ "error": "에러_코드" }` 형태를 사용한다.

### 1.4 Phase 1 체크리스트

- [ ] API Gateway에서 로그인 사용자(JWT) 검증 후 챗봇 호출
- [ ] `chatbot_service` 헬스체크 확인 (`GET /health`)
- [ ] 429/503 에러가 Gateway에서 `{error: ...}` 형식으로 내려오는지 확인
- [ ] `docker-compose.dev.yml`에서 gateway↔chatbot 네트워크 통신 확인

---

## 2. Phase 1 구현 구성요소(현재 작업된 내용)

### 2.1 파이프라인(데이터 준비)

- Content Service
  - 요약 저장 성공 후 `post.embedding_requested` 이벤트 발행
- Embedding Worker
  - `post.embedding_requested` 소비
  - 텍스트 청킹 + 임베딩 생성
  - MongoDB 기반 임베딩 캐시 적용
  - `post.embedding_response` 발행
- Chatbot Service
  - `post.embedding_response` 소비
  - Qdrant에 청크 임베딩 upsert
  - upsert 성공 시 `post.embedding_applied` 발행
- Content Service
  - `post.embedding_applied` 소비
  - Post 문서에 `status.embedded=true`, `embedding` 메타데이터 반영

### 2.2 검색/응답 생성

- Chatbot Service
  - 쿼리 임베딩 → Qdrant 검색 → LLM 답변 생성
  - 외부 AI API 장애/Rate limit 상황을 `429/503`으로 매핑

### 2.3 배포/로컬 실행

- `docker-compose.dev.yml`, `docker-compose.prod.yml`에
  - `embedding_worker`
  - `chatbot_service`
  - (Vector DB) `qdrant` 연동

#### 관련 환경변수(초안)

- API Gateway → Chatbot Service
  - `CHATBOT_SERVICE_BASE_URL`
    - 기본값: `http://chatbot_service:8003`
    - Gateway 컨테이너에서 내부 네트워크로 접근하는 주소

---

## 3. Phase 2 계획(유저 기능/비용 통제)

이벤트 드리븐 아키텍처 기반 구조로 작업

### 3.1 크레딧/쿼터 도입

- 사용자별 크레딧 차감 정책 정의
  - 요청 1회당 비용
  - 모델별 비용 가중치(선택)
- Gateway 레벨 rate limit + quota 체크
- 남은 크레딧 조회 API

### 3.2 대화 내역(History/Library)

- `GET /api/v1/chatbot/history` 또는 `GET /api/v1/chatbot/library` 추가
- 저장 스키마(초안)
  - `user_code`, `query`, `answer`, `sources`, `created_at`

---

## 4. Phase 3 계획(개인화/품질 고도화)

- **검색 품질**
  - 재랭킹(Recency/태그/블로그 가중치)
  - 문서 chunk 전략 개선
  - 오프라인 평가 데이터셋/회귀 테스트
- **개인화**
  - 유저 선호 태그/블로그 기반 컨텍스트 강화
  - 북마크/읽음 기록을 활용한 추천
- **운영/관측성**
  - gateway↔chatbot latency 분해 로그
  - 429/503 알람 포인트
  - 비용/사용량 대시보드
