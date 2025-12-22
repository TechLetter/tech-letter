# 프론트엔드 API 명세: 챗봇 Phase 2

## 개요

Phase 2에서 추가된 **크레딧 시스템**과 **채팅 세션** API 명세입니다.

---

## 1. 데이터 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                        채팅 플로우                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 세션 생성 (선택)                                            │
│     POST /chatbot/sessions → session_id 획득                   │
│                                                                 │
│  2. 채팅 요청                                                   │
│     POST /chatbot/chat { query, session_id? }                  │
│                                                                 │
│  3. 응답 처리                                                   │
│     - 성공: answer, consumed_credits, remaining_credits 수신   │
│     - 실패: error 코드에 따른 분기 처리                         │
│                                                                 │
│  4. 이전 대화 조회 (선택)                                        │
│     GET /chatbot/sessions/:id → messages 배열                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. API 명세

### 2.1 사용자 프로필 조회

**`GET /api/v1/users/profile`**

| 필드      | 타입     | 설명                      |
| --------- | -------- | ------------------------- |
| `credits` | `number` | 현재 잔여 크레딧 (0 이상) |

```json
{
  "user_code": "google:xxx",
  "name": "홍길동",
  "email": "user@example.com",
  "profile_image": "https://...",
  "role": "user",
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:00Z",
  "credits": 9
}
```

---

### 2.2 세션 목록 조회

**`GET /api/v1/chatbot/sessions`**

**Query Parameters:**

| 파라미터    | 타입     | 필수 | 기본값 | 설명             |
| ----------- | -------- | ---- | ------ | ---------------- |
| `page`      | `number` | ❌   | 1      | 페이지 번호      |
| `page_size` | `number` | ❌   | 20     | 페이지당 항목 수 |

**Response:**

```json
{
  "total": 5,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": "abc123",
      "title": "React 성능 최적화 질문...",
      "messages": [],
      "created_at": "2025-12-22T10:00:00Z",
      "updated_at": "2025-12-22T10:30:00Z"
    }
  ]
}
```

---

### 2.3 세션 생성

**`POST /api/v1/chatbot/sessions`**

**Request Body:** 없음

**Response:**

```json
{
  "id": "abc123",
  "title": "New Chat",
  "messages": [],
  "created_at": "2025-12-22T10:00:00Z",
  "updated_at": "2025-12-22T10:00:00Z"
}
```

---

### 2.4 세션 상세 조회

**`GET /api/v1/chatbot/sessions/:id`**

**Path Parameters:**

| 파라미터 | 타입     | 설명    |
| -------- | -------- | ------- |
| `id`     | `string` | 세션 ID |

**Response:**

```json
{
  "id": "abc123",
  "title": "React 성능 최적화 질문...",
  "messages": [
    {
      "role": "user",
      "content": "React 성능 최적화 방법은?",
      "created_at": "..."
    },
    { "role": "assistant", "content": "React 성능을...", "created_at": "..." }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

---

### 2.5 세션 삭제

**`DELETE /api/v1/chatbot/sessions/:id`**

**Path Parameters:**

| 파라미터 | 타입     | 설명    |
| -------- | -------- | ------- |
| `id`     | `string` | 세션 ID |

**Response:** `200 OK` (body 없음)

---

### 2.6 채팅 요청

**`POST /api/v1/chatbot/chat`**

**Request Body:**

| 필드         | 타입     | 필수 | 설명                                    |
| ------------ | -------- | ---- | --------------------------------------- |
| `query`      | `string` | ✅   | 사용자 질문                             |
| `session_id` | `string` | ❌   | 세션 ID (제공 시 해당 세션에 대화 저장) |

```json
{
  "query": "React 성능 최적화 방법은?",
  "session_id": "abc123"
}
```

**Response (성공):**

| 필드                | 타입     | 설명                        |
| ------------------- | -------- | --------------------------- |
| `answer`            | `string` | AI 응답                     |
| `consumed_credits`  | `number` | 이번 요청에서 소모된 크레딧 |
| `remaining_credits` | `number` | 요청 후 남은 크레딧         |

```json
{
  "answer": "React 성능 최적화를 위해...",
  "consumed_credits": 1,
  "remaining_credits": 8
}
```

---

## 3. 에러 처리

| HTTP | error                  | 설명                     | 권장 처리              |
| ---- | ---------------------- | ------------------------ | ---------------------- |
| 400  | `invalid_request`      | 요청 형식 오류           | 입력값 검증            |
| 400  | `invalid_session_id`   | 존재하지 않는 session_id | 새 세션 생성 후 재시도 |
| 402  | `insufficient_credits` | 크레딧 부족              | 사용자에게 안내        |
| 503  | `chatbot_unavailable`  | 챗봇 서비스 장애         | 재시도 안내            |

**에러 응답 형식:**

```json
{
  "error": "insufficient_credits"
}
```
