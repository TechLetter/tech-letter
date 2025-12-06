# 내부용 API 스펙 규칙

이 문서는 Tech-Letter 내부 마이크로서비스 간 HTTP API 규칙을 정의한다.

- 대상 서비스
  - API Gateway (Go, Gin)
  - Content Service (Python, FastAPI)
  - User Service (Python, FastAPI)
- 목표
  - 서비스 간 통신 규칙을 명확히 하고, 새로운 엔드포인트 추가 시 일관성을 유지한다.

---

## 1. 버전 / 경로 규칙

- **BasePath**
  - 모든 내부 REST API는 `/api/v1` 를 기본 prefix 로 사용한다. (필요에 따라 v2, v3 등 버전 추가 가능)
  - 예시
    - Content Service: `/api/v1/posts`, `/api/v1/blogs`, `/api/v1/filters`
    - User Service: `/api/v1/users`
- **리소스 경로 네이밍**
  - 복수형 명사 사용: `posts`, `blogs`, `users`
  - 리소스 식별자는 path param 으로 표현: `/posts/{post_id}`, `/users/{user_code}`
  - 추가 액션은 하위 경로로 표현: `/posts/{post_id}/view`

---

## 2. 공통 원칙

- **전송 포맷**
  - 요청/응답은 모두 `application/json; charset=utf-8` 사용
  - 키 이름은 snake_case 사용: `user_code`, `blog_id`, `created_at` 등
- **시간 포맷**
  - 시간은 ISO 8601 문자열(UTC) 사용
  - 예: `2025-01-01T12:00:00Z`
- **DTO 기반 설계**
  - 외부 공개 API (Gateway)는 Go `dto` 패키지의 DTO 구조체를 기준으로 스펙 정의
  - 내부 FastAPI 서비스는 `app/api/schemas` 내 Pydantic 모델을 DTO로 사용
  - 엔드포인트마다 "도메인 모델"과 "전송용 DTO"를 분리한다.

---

## 3. HTTP 메서드 규칙

- **GET**
  - 리소스 조회 전용
  - 부수효과(side-effect) 없음
- **POST**
  - 리소스 생성 또는 명확한 액션 실행에 사용
  - 예: `/posts/{post_id}/view` (조회수 증가), `/users/upsert` (유저 upsert)
- **PUT / PATCH / DELETE**
  - 현재 내부 서비스에서는 사용하지 않음
  - 향후 사용 시 아래 원칙 권장
    - PUT: 전체 리소스 교체
    - PATCH: 리소스 일부 수정
    - DELETE: 리소스 삭제

---

## 4. HTTP Status Code 규칙

### 4.1 공통 규칙

- **2xx Success**

  - `200 OK`
    - 모든 정상적인 요청에 대한 처리 결과

- **4xx Client Error**

  - `400 Bad Request`
    - 형식은 맞지만 도메인 규칙을 위반한 요청에 사용
    - 현재는 내부 서비스에서 직접 사용하지 않고, FastAPI 의 `422` 또는 `HTTPException` 으로 표현
  - `401 Unauthorized`, `403 Forbidden`
    - 인증/인가 실패는 API Gateway 레이어에서 처리
    - 내부 마이크로서비스는 보통 신뢰된 네트워크에서만 호출된다는 가정
  - `404 Not Found`
    - 리소스가 존재하지 않는 경우 사용
    - 현재 구현 예시
      - Content Service: 포스트/PlainText/HTML 조회, 조회수 증가 시 대상 없음
      - User Service: 유저 프로필 없음
  - `422 Unprocessable Entity`
    - FastAPI/Pydantic 요청 검증 실패 시 자동 반환
    - 필드 타입/범위 제약 위반 등

- **5xx Server Error**
  - `500 Internal Server Error`
    - 처리 중 예상치 못한 예외 발생 시 사용 (FastAPI 기본 동작)

## 5. 에러 응답 바디 규칙

### 5.1 내부 FastAPI 서비스

- `HTTPException` 사용 시
  - 형태: `{ "detail": "에러 메시지" }`
  - 예: `{ "detail": "post not found" }`, `{ "detail": "user not found" }`
- 검증 실패(422)
  - FastAPI/Pydantic 기본 형식 사용
    - 예: `{ "detail": [{"loc": [...], "msg": "...", "type": "..."}, ...] }`

### 5.2 API Gateway (외부 공개 API)

- 공통 에러 DTO (Go `dto.ErrorResponseDTO`)
  - 형태: `{ "error": "에러_코드" }`
  - 예: `{"error": "invalid_token"}`, `{"error": "user_not_found"}`
- 단순 메시지 DTO (Go `dto.MessageResponseDTO`)
  - 형태: `{ "message": "메시지" }`
  - 예: `{"message": "view count incremented successfully"}`

> 내부 서비스는 사람이 읽기 쉬운 detail 메시지를 유지하고, 외부로 노출되는 에러 코드는 API Gateway 레이어에서 DTO 형식으로 변환/매핑하는 것을 기본 원칙으로 한다.

---

## 6. 페이징 / 필터링 규칙

- **쿼리 파라미터**
  - 페이지네이션
    - `page`: 1부터 시작 (기본값 1)
    - `page_size`: 기본 20, 최대 100
  - 다중 필터
    - `categories`, `tags` 등은 배열 형태 쿼리로 전달: `?tags=python&tags=go`
- **응답 형태 예시 (목록)**
  - Content Service: `ListPostsResponse`, `ListBlogsResponse` 등
  - API Gateway: `PaginationPostDTO`, `PaginationBlogDTO` 등
    - 공통 필드: `data`(또는 `items`), `page`, `page_size`, `total`

---

## 7. 트레이싱 / 공통 헤더

- 요청/응답에는 다음 헤더를 사용해 트레이싱 정보를 전달한다.
  - `X-Request-Id`: 요청 단위 추적 ID
  - `X-Span-Id`: 서비스 간 호출 체인 추적 ID
- Go/Gin, FastAPI 양쪽 모두 공통 미들웨어에서 이 헤더를 처리해 로그에 남기며,  
  엔드포인트 구현에서는 별도 처리를 하지 않아도 된다.

---

## 8. 새로운 내부 API 추가 시 체크리스트

1. 경로가 `/api/v1/...` 규칙을 따르는지 확인 (필요에 따라 v2, v3 등 버전 추가 가능)
2. 리소스/액션 이름이 명확하고 복수형/하위 경로 규칙을 따르는지 확인
3. 요청/응답 DTO를 별도 스키마(Pydantic/Go struct)로 정의했는지 확인
4. 성공/에러 status code가 본 문서의 규칙과 일치하는지 확인
5. 에러 응답 형식이
   - 내부 서비스: `{ "detail": ... }`
   - 외부 공개 API: `{ "error": ... }` / `{ "message": ... }`  
     로 일관되는지 확인
6. 필요한 경우 Swagger(Swagger/OpenAPI) 주석 또는 FastAPI `response_model`, `summary`, `description` 을 추가해 문서화
