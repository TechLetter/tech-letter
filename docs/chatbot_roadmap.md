# 챗봇 기능 명세 및 로드맵

이 문서는 Tech-Letter 챗봇 기능의 현재 구현 상태와 다음 단계 계획을 정리한다.

- 기준일: **2026-02-16**
- 현재 상태: **Phase 1 완료 + Phase 2 핵심 기능 구현 완료**

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
  - 로그인된 사용자(JWT 유효)만 호출 가능하다.

### 1.2 응답 포맷 정책

- 현재 외부 공개 API에서 응답 포맷 강제는 아래만 적용한다.
  - `pagination`
  - `error` (`{"error": "..."}`)
  - `message` (`{"message": "..."}`)
- 챗봇 성공 응답은 `sources`를 외부로 노출하지 않으며 다음 필드를 반환한다.
  - `answer`
  - `consumed_credits`
  - `remaining_credits`

### 1.3 에러 코드 정책 (API Gateway)

- `401`: 로그인 필요/토큰 오류
- `400`: 요청 형식 오류
- `429`: AI API rate limit (일시적인 제한)
- `503`: 챗봇/AI 제공자 일시 장애
- `500`: 기타 서버 오류

모든 에러 응답은 Gateway 공통 규칙에 따라 `{ "error": "에러_코드" }` 형태를 사용한다.

### 1.4 Phase 1 체크리스트

- [x] API Gateway에서 로그인 사용자(JWT) 검증 후 챗봇 호출
- [x] `chatbot_service` 헬스체크 확인 (`GET /health`)
- [x] 429/503 에러를 Gateway에서 `{error: ...}` 형식으로 정규화
- [x] `docker-compose.dev.yml` 기준 gateway↔chatbot 내부 네트워크 통신 구성

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

## 3. Phase 2 구현 현황 (유저 기능/비용 통제)

이벤트 드리븐 아키텍처 기반 구조로 구현되었다.

### 3.1 크레딧/비용 통제 (구현 완료)

- 요청 1회당 1크레딧 차감(`POST /api/v1/credits/{user_code}/consume`)
- 채팅 실패 시 환불 처리(`POST /api/v1/credits/{user_code}/log-chat`, `success=false`)
- 채팅 성공/실패 이벤트 발행(`tech-letter.chat`)
- 관리자 크레딧 수동 지급(`POST /api/v1/admin/users/:user_code/credits`)
- 로그인 시 일일 크레딧 지급(`POST /api/v1/credits/{user_code}/grant-daily`)

### 3.2 대화 세션 관리 (구현 완료)

- `GET /api/v1/chatbot/sessions`: 세션 목록 조회
- `POST /api/v1/chatbot/sessions`: 세션 생성
- `GET /api/v1/chatbot/sessions/:id`: 세션 상세 조회
- `DELETE /api/v1/chatbot/sessions/:id`: 세션 삭제
- `chat.completed` 이벤트 소비를 통해 사용자/어시스턴트 메시지를 세션에 적재

### 3.3 Phase 2 잔여 작업 (미구현)

- Gateway 레벨 전역 rate limit/quota 정책
- 별도 `history/library` API 명칭으로의 정리(현재는 `sessions` API 사용)
- 비용/사용량 대시보드 및 운영 지표 자동화

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
