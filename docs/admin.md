# Admin Features & API Specification

이 문서는 Tech-Letter 프로젝트의 관리자(Admin) 기능 및 API 명세를 기술합니다.

## 1. 개요

관리자 기능은 시스템 운영자(`admin`)가 콘텐츠(블로그, 포스트)와 사용자를 관리할 수 있는 기능을 제공합니다. 모든 관리자 API는 **API Gateway**를 통해 노출되며, 각 **Microservice**(Content Service, User Service)로 요청을 프록시하거나 조합하여 처리합니다.

## 2. 인증 및 권한 (Authentication & Authorization)

- **미들웨어**: `AdminAuthMiddleware` (API Gateway)
- **접근 제어**:
  - 요청 헤더의 `Authorization: Bearer <JWT Token>`을 검증합니다.
  - JWT 토큰 내의 `role` 클레임이 반드시 `"admin"`이어야 합니다.
  - 조건 만족 시 통과, 실패 시 `401 Unauthorized` 또는 `403 Forbidden`을 반환합니다.

## 3. Base URL

모든 관리자 API는 다음 경로 하위에 위치합니다.

```
/api/v1/admin
```

## 4. 공통 응답 (Common Responses)

### 성공 응답 (Simple Success)

데이터 반환이 없는 작업(삭제, 트리거 등)의 성공 응답은 `MessageResponseDTO` 형식을 따릅니다.

```json
{
  "message": "작업 성공 메시지"
}
```

### 에러 응답 (Error)

모든 API의 에러 응답은 `ErrorResponseDTO` 형식을 따릅니다.

```json
{
  "error": "에러 상세 메시지"
}
```

## 5. API Endpoints

### 5.1. Posts (포스트 관리)

#### 5.1.1. 포스트 목록 조회 (전체)

공개 API와 달리 필터링 없이 전체 포스트를 최신순으로 조회할 수 있습니다 (필요 시 필터 추가 가능).

- **Method**: `GET /api/v1/admin/posts`
- **Query Parameters**:
  - `page`: 페이지 번호 (default: 1)
  - `page_size`: 페이지 크기 (default: 20)
  - `status_ai_summarized`: AI 요약 완료 여부 (`true`/`false`)
  - `status_embedded`: 임베딩 완료 여부 (`true`/`false`)
- **Response**: `dto.PaginationAdminPostDTO`
- **Response Schemas**:
  ```json
  {
    "total": 120,
    "page": 1,
    "page_size": 20,
    "data": [
      {
        "id": "64f1...",
        "created_at": "2025-12-15T01:00:00+00:00",
        "updated_at": "2025-12-15T02:00:00+00:00",
        "status": {
          "ai_summarized": true,
          "embedded": false
        },
        "view_count": 10,
        "blog_id": "...",
        "blog_name": "Tech Blog",
        "title": "Post Title",
        "link": "https://...",
        "published_at": "2025-12-15T00:00:00+00:00",
        "thumbnail_url": "https://...",
        "aisummary": {
          "categories": ["Backend", "DevOps"],
          "tags": ["kubernetes", "docker"],
          "summary": "요약 내용...",
          "model_name": "gpt-4o-mini",
          "generated_at": "2025-12-15T01:30:00+00:00"
        },
        "embedding": {
          "model_name": "text-embedding-3-small",
          "collection_name": "posts",
          "vector_dimension": 1536,
          "chunk_count": 5,
          "embedded_at": "2025-12-15T01:45:00+00:00"
        }
      }
    ]
  }
  ```

#### 5.1.2. 포스트 수동 생성

크롤링 외에 관리자가 직접 포스트를 등록할 수 있습니다. 생성 직후 **AI 요약 이벤트**(`post.summary_requested`)가 자동으로 발행됩니다.

- **Method**: `POST /api/v1/admin/posts`
- **Request Body**:
  ```json
  {
    "title": "게시글 제목",
    "link": "https://example.com/post-link",
    "blog_id": "<BlogID Hex String>"
  }
  ```
- **Response**:
  ```json
  {
    "id": "<Created Post ID>",
    "title": "게시글 제목"
  }
  ```

#### 5.1.3. 포스트 삭제

- **Method**: `DELETE /api/v1/admin/posts/:id`
- **Response**:
  ```json
  { "message": "post deleted successfully" }
  ```

#### 5.1.4. AI 요약 트리거 (재시도/수동)

특정 포스트에 대해 AI 요약 작업을 강제로 다시 트리거합니다. (`post.summary_requested` 이벤트 발행)

- **Method**: `POST /api/v1/admin/posts/:id/summarize`
- **Response**:
  ```json
  { "message": "summary triggered successfully" }
  ```

#### 5.1.5. AI 임베딩 트리거 (재시도/수동)

특정 포스트에 대해 벡터 임베딩 생성 작업을 강제로 다시 트리거합니다. (`post.embedding_requested` 이벤트 발행)

- **Method**: `POST /api/v1/admin/posts/:id/embed`
- **Response**:
  ```json
  { "message": "embedding triggered successfully" }
  ```

### 5.2. Blogs (블로그 관리)

#### 5.2.1. 블로그 목록 조회

- **Method**: `GET /api/v1/admin/blogs`
- **Query Parameters**:
  - `page`: 페이지 번호
  - `page_size`: 페이지 크기
- **Response**: `dto.Pagination[dto.BlogDTO]`
  ```json
  {
    "total": 5,
    "items": [
      {
        "id": "...",
        "name": "Tech Blog",
        "url": "https://blog.example.com"
      }
    ]
  }
  ```

### 5.3. Users (사용자 관리)

#### 5.3.1. 사용자 목록 조회

가입된 모든 사용자를 조회합니다.

- **Method**: `GET /api/v1/admin/users`
- **Query Parameters**:
  - `page`: 페이지 번호
  - `page_size`: 페이지 크기
- **Response**:
  ```json
  {
    "total": 100,
    "items": [
      {
        "user_code": "google:...",
        "email": "user@example.com",
        "name": "User Name",
        "role": "user",
        "created_at": "...",
        "updated_at": "..."
      }
    ]
  }
  ```

## 6. 구현 상세 (Microservices)

### 6.1. API Gateway (Go)

- `cmd/api/middleware/admin_auth.go`: JWT Role 검증 로직.
- `cmd/api/handlers/admin_handlers.go`: Admin용 핸들러 모음. `PostService`, `AuthService`, `BlogService`를 통해 각 마이크로서비스 호출.
- `cmd/api/clients`: `contentclient`, `userclient`에 Admin용 메서드 추가. 각 클라이언트는 마이크로서비스의 일반(`Generic`) CRUD API를 호출함.

### 6.2. Content Service (Python)

- **Admin 전용 Router 없음**: 관리자 기능은 일반적인 리소스 관리(`Resource Management`) API로 통합됨.
- `app/api/v1/posts.py`:
  - `POST /posts`: 포스트 생성 (이벤트 발행 포함).
  - `DELETE /posts/:id`: 포스트 삭제.
  - `POST /posts/:id/summarize`, `POST /posts/:id/embed`: 이벤트 트리거.
- `app/services/posts_service.py`: `PostsService`가 생성, 삭제, 이벤트 발행 로직을 통합 관리.

### 6.3. User Service (Python)

- **Admin 전용 Router 없음**.
- `app/api/v1/users.py`:
  - `GET /users`: 전체 유저 목록 조회 API 추가.
- `app/services/users_service.py`: `list_users` 메서드 추가 (Pagination 지원).
- `app/repositories/user_repository.py`: `list` 메서드 추가.

## 7. Frontend (예정)

- 별도의 Admin Web App 또는 기존 프론트엔드 내 `/admin` 라우트에서 위 API들을 사용.
- 구글 로그인 후, `role`이 `admin`인 계정만 접근 가능하도록 처리 필요.
