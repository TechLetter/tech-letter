# 인증 및 프론트엔드 연동 가이드

이 문서는 Tech-Letter 서비스의 **API Gateway 인증/인가 플로우**와
**프론트엔드 연동 규칙**을 정리한 문서입니다.

- 인증 방식: Google OAuth + JWT(HS256)
- 상태 유지는 **오직 Authorization 헤더**로만 수행 (쿠키/세션 미사용)

---

## 1. 전체 플로우 개요

1. 프론트엔드는 `VITE_API_BASE_URL` 을 API Gateway 주소로 사용한다.
2. 사용자가 "Google 로그인" 버튼을 누르면 전체 페이지를
   `GET {VITE_API_BASE_URL}/api/v1/auth/google/login` 으로 이동시킨다.
3. Google OAuth 인증이 끝나면 Google 이 Gateway 의
   `GET /api/v1/auth/google/callback` 으로 리다이렉트한다.
4. Gateway 는 Google 토큰 → userinfo → User Service `upsert` → JWT 생성까지 처리한다.
5. Gateway 는 생성한 JWT를 User Service 의 `POST /api/v1/login-sessions` 로 전달해 짧은 TTL의 로그인 세션을 생성한다.
6. 성공 시 `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>?session=<SESSION_ID>` 로 프론트로 리다이렉트한다.
7. 실패 시 `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>` (쿼리 파라미터 없이) 로 리다이렉트한다.
8. 프론트는 `/login/success` 페이지에서 `?session=<SESSION_ID>` 를 읽어
   `POST /api/v1/auth/session/exchange` 로 JWT 액세스 토큰을 교환한 뒤 localStorage 등에 저장하고,
   이후 모든 API 요청에 `Authorization: Bearer <JWT>` 헤더를 붙인다.

---

## 2. 엔드포인트 계약

### 2.1 `GET /api/v1/auth/google/login`

- **용도**: Google OAuth 로그인 플로우 시작
- **동작**
  - OAuth `state` 를 생성하여 쿠키(`oauth_state`)에 저장한다. (CSRF 방지용)
  - Google OAuth 로그인 URL로 `302` 리다이렉트한다.
  - 응답 바디는 사용하지 않고, 항상 리다이렉트만 사용한다.
- **실패 처리**
  - 내부 에러로 `state` 생성에 실패해도,
    `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>` 로 토큰 없이 리다이렉트한다.

프론트 예시:

```ts
// 로그인 버튼 클릭 핸들러
window.location.href = `${VITE_API_BASE_URL}/api/v1/auth/google/login`;
```

---

### 2.2 `GET /api/v1/auth/google/callback`

- **용도**: Google 이 호출하는 OAuth 콜백 엔드포인트
- **프론트는 직접 호출하지 않는다.**
- **입력**
  - 쿼리 파라미터: `state`, `code`
  - 쿠키: `oauth_state` (로그인 시작 시 저장됨)
- **동작**
  1. `state`, `code` 존재 여부 검사
  2. 쿠키의 `oauth_state` 와 쿼리의 `state` 비교 (CSRF 방지)
  3. Google OAuth 토큰 교환 (`code` → access token)
  4. Google userinfo 조회
  5. User Service `POST /api/v1/users/upsert` 호출
  6. 응답의 `user_code`, `role` 로 JWT 생성
  7. 생성한 JWT를 User Service 의 `POST /api/v1/login-sessions` 로 전달해 짧은 TTL의 로그인 세션을 생성
- **리다이렉트 규칙**
  - **성공:** `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>?session=<SESSION_ID>`
  - **실패:** `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>` (쿼리 파라미터 없음)

프론트는 `/login/success` 페이지에서 `session` 유무로 성공/실패를 1차 판별하고,
성공 시 `POST /api/v1/auth/session/exchange` 로 JWT를 교환한다.

---

### 2.3 `POST /api/v1/auth/session/exchange`

- **용도**: 짧은 TTL을 가진 로그인 세션 ID를 JWT 액세스 토큰으로 교환
- **프론트만 호출하며, 백엔드는 직접 호출하지 않는다.**
- **입력**
  - 바디(JSON): `{ "session": "<SESSION_ID>" }`
- **응답 예시**

```json
{ "access_token": "<JWT_ACCESS_TOKEN>" }
```

- **에러 규칙**
  - 세션 만료/미존재 → `400` + 에러 메시지 (예: "로그인 세션이 만료되었거나 유효하지 않습니다.")

---

### 2.4 `GET /api/v1/users/profile`

- **용도**: 현재 로그인한 유저 정보 조회
- **입력**
  - 헤더: `Authorization: Bearer <JWT>`
  - 바디 없음 (단순 GET)
- **응답 예시**

```json
{
  "user_code": "google:xxxx-uuid",
  "provider": "google",
  "provider_sub": "<google-sub>",
  "email": "user@example.com",
  "name": "홍길동",
  "profile_image": "https://...",
  "role": "user",
  "created_at": "2025-12-06T01:23:45Z",
  "updated_at": "2025-12-06T01:23:45Z"
}
```

- **에러 규칙**
  - 토큰 누락/형식 오류/검증 실패 → `401`
  - 유저 미존재 → `404`
  - 서버 오류 → `5xx`

프론트 예시:

```ts
const token = localStorage.getItem("access_token");

const res = await fetch(`${VITE_API_BASE_URL}/api/v1/users/profile`, {
  headers: {
    Authorization: `Bearer ${token}`,
  },
});

if (!res.ok) {
  // 401/403/5xx 인 경우: 토큰 제거 후 "세션 만료" 처리
}

const profile = await res.json();
```

---

### 2.5 `DELETE /api/v1/users/me`

- **용도**: 로그인한 사용자의 계정(프로필 + 북마크)을 삭제하는 **회원 탈퇴** 엔드포인트
- **입력**
  - 헤더: `Authorization: Bearer <JWT>`
  - 바디 없음
- **외부 계약 (Gateway)**
  - 클라이언트는 항상 `DELETE /api/v1/users/me` 만 호출한다.
  - Gateway 는 JWT 를 검증하고, `sub` 클레임에서 `user_code` 를 추출한다.
  - 추출한 `user_code` 를 사용해 User Service 의 내부 API 를 호출한다.
- **내부 동작 (User Service)**
  - `DELETE /api/v1/users/{user_code}`
    - users 컬렉션에서 해당 유저 도큐먼트 삭제
    - bookmarks 컬렉션에서 해당 `user_code` 의 북마크 전부 삭제
    - User Service 는 인증/인가 판단 없이 **순수 CRUD 역할**만 수행한다.
- **응답 규칙 (Gateway 기준)**
  - **성공:** `200 OK`
  - **JWT 누락/검증 실패:** `401 Unauthorized`
  - **유저 미존재(이미 탈퇴된 계정 포함):** `404 Not Found`
  - **서버 오류:** `5xx`

프론트 예시:

```ts
const token = localStorage.getItem("access_token");

const res = await fetch(`${VITE_API_BASE_URL}/api/v1/users/me`, {
  method: "DELETE",
  headers: {
    Authorization: `Bearer ${token}`,
  },
});

if (res.ok) {
  // 200: 탈퇴 성공 → 로컬 토큰/프로필 제거 후 랜딩 페이지로 이동
  localStorage.removeItem("access_token");
  window.location.href = "/";
} else if (res.status === 404) {
  // 이미 탈퇴된 계정 등: 유저 미존재 → 토큰 제거 후 랜딩 페이지 이동
  localStorage.removeItem("access_token");
  window.location.href = "/";
} else if (res.status === 401) {
  // 인증 만료/무효: 일반 로그아웃 처리
  localStorage.removeItem("access_token");
}
```

---

## 3. JWT 스펙

- **알고리즘**: `HS256`
- **만료 시간**: 24시간
- **클레임**
  - `sub`: User Service 가 반환한 `user_code` (예: `google:<uuid>`)
  - `role`: `"user"` 또는 `"admin"`
  - `iss`: 기본값 `"tech-letter"` (환경변수 `JWT_ISSUER` 로 변경 가능)
  - `exp`: 만료 시각(UNIX timestamp)

Gateway 는 User Service 의 `upsert` 응답으로 받은 `user_code`, `role` 을 그대로
`sub`, `role` 클레임에 넣어 JWT 를 생성한다.

프론트는 `/login/success?session=<SESSION_ID>` 로 전달된 세션 ID를
`POST /api/v1/auth/session/exchange` 로 교환해 받은 JWT를 저장하고,
이후 모든 API 호출에서 `Authorization: Bearer <JWT>` 로 전달한다.

---

## 4. CORS 및 보안 정책

API Gateway (`cmd/api/main.go`) 는 `github.com/rs/cors` 를 사용해 CORS 를 설정한다.

- 허용 Origin: `CORS_ALLOWED_ORIGINS` 환경변수 (쉼표 구분)
  - 예: `http://localhost:5173,https://tech-letter.duckdns.org`
  - 미설정 시 개발 편의를 위해 `*` 허용 (단, 쿠키는 사용하지 않음)
- 허용 메서드: `GET, POST, PUT, DELETE, OPTIONS`
- 허용 헤더: `Authorization, Content-Type`
- `AllowCredentials = false` 로 설정하여 브라우저 쿠키/withCredentials 를 사용하지 않는다.

즉, **JWT는 항상 헤더로만 전달**되고, 인증 상태를 나타내는 쿠키는 사용하지 않는다.

---

## 5. 환경 변수 정리

### 5.1 Google OAuth

- `GOOGLE_OAUTH_CLIENT_ID` (필수)
- `GOOGLE_OAUTH_CLIENT_SECRET` (필수)
- `GOOGLE_OAUTH_REDIRECT_URL` (필수)
  - 예: `http://localhost:8080/api/v1/auth/google/callback`
  - 예: `https://tech-letter.duckdns.org/api/v1/auth/google/callback`

### 5.2 JWT

- `JWT_SECRET` (필수)
  - HS256 서명을 위한 시크릿 문자열
  - 충분히 긴 랜덤 값 권장 (예: `openssl rand -base64 32`)
- `JWT_ISSUER` (선택)
  - 기본값: `tech-letter`

### 5.3 로그인 성공 리다이렉트

- `AUTH_LOGIN_SUCCESS_REDIRECT_URL` (필수)
  - 예: `http://localhost:5173/login/success`
  - 예: `https://tech-letter.duckdns.org/login/success`

### 5.4 CORS

- `CORS_ALLOWED_ORIGINS` (선택)
  - 프론트 도메인 목록 (쉼표 구분)
  - 예: `http://localhost:5173,https://tech-letter.duckdns.org`

---

## 6. 프론트엔드 요약

프론트 기준 한 줄 요약:

> `/login/success?session=<SESSION_ID>` 쿼리로 넘어온 세션 ID를
> `POST /api/v1/auth/session/exchange` 로 JWT 액세스 토큰으로 교환해 localStorage 에 저장하고,
> 이후 모든 API 호출에서 `Authorization: Bearer <JWT>` 헤더를 사용해 `/api/v1/users/profile` 로 현재 유저 정보를 가져온다.

- 로그인 시작: `GET /api/v1/auth/google/login` 으로 페이지 이동
- 콜백/세션 생성: Gateway 가 Google OAuth 콜백을 처리하고 로그인 세션 생성 후 `/login/success?session=<SESSION_ID>` 로 리다이렉트
- 토큰 교환: 프론트가 `POST /api/v1/auth/session/exchange` 로 세션을 JWT로 교환
- 프로필 조회: `GET /api/v1/users/profile` + `Authorization: Bearer <JWT>`

---

## 7. 과거 문제 상황과 TTL 기반 임시 로그인 세션

- **이전 구현**

  - Google OAuth 콜백 이후 Gateway 가 JWT 를 바로 발급하고,
    `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>?token=<JWT>` 형태로 프론트에 전달했다.
  - 프론트는 `/login/success?token=<JWT>` 의 `token` 쿼리 파라미터를 읽어 localStorage 에 저장했다.

- **문제점**

  - JWT 가 URL 쿼리 파라미터에 노출되면서 다음과 같은 위험이 있었다.
    - 브라우저 히스토리 / 주소창 / 캡처 화면 등에 토큰이 그대로 남음
    - 서버 액세스 로그, 리버스 프록시 로그 등에 전체 URL 이 기록될 수 있음
    - 다른 페이지로 이동 시 Referer 헤더에 토큰이 포함될 수 있음
    - URL 을 그대로 공유(복사/붙여넣기, 채팅, 이슈 링크 등)하면 토큰 유출 가능
  - 요구사항: **JWT는 절대 URL로 노출하지 말고, 항상 HTTPS 바디나 Authorization 헤더로만 전달할 것.**

- **개선 방향**

  - JWT 자체를 URL에 실지 않고, **짧은 TTL(Time-To-Live)을 가진 임시 로그인 세션을 추가 계층으로 둔다.**
  - Gateway 는 JWT 를 발급한 뒤, User Service 의 `login_sessions` 컬렉션에 JWT 를 그대로 저장하고,
    프론트에는 `session_id` 만 전달한다.

- **MongoDB TTL 인덱스 활용**

  - `login_sessions` 컬렉션 스키마 (도메인 모델 기준):
    - `session_id: str` — 프론트와 Gateway 사이에서만 사용하는 세션 식별자
    - `jwt_token: str` — 발급된 JWT 액세스 토큰 문자열
    - `expires_at: datetime` — 세션 만료 시각
  - MongoDB 에서 `expires_at` 필드에 대해 TTL 인덱스를 설정한다.
    - 예시: `createIndex({ expires_at: 1 }, { expireAfterSeconds: 0 })`
    - TTL 인덱스는 백그라운드에서 주기적으로 만료된 도큐먼트를 삭제한다.
  - 애플리케이션 레벨에서도 한 번 더 만료를 확인해 TTL 삭제 지연(time window)을 방어한다.
    - `expires_at <= now` 인 경우, 세션이 있어도 만료된 것으로 간주하고 JWT 를 반환하지 않는다.

- **최종 플로우 (보안 관점)**

  - Gateway:
    - Google OAuth 콜백 처리 후 JWT 발급
    - `session_id`, `expires_at` 을 Gateway 에서 생성
    - `POST /api/v1/login-sessions` (user-service) 로 `{ session_id, jwt_token, expires_at }` 저장
    - 프론트에는 `/login/success?session=<SESSION_ID>` 로만 리다이렉트 (JWT 미포함)
  - 프론트엔드:
    - `/login/success` 에서 `session` 쿼리 파라미터를 읽는다.
    - `POST /api/v1/auth/session/exchange` 로 `{ session: <SESSION_ID> }` 를 전송해 JWT 을 교환한다.
    - 응답의 `access_token` 을 localStorage 등에 저장하고 이후 Authorization 헤더로만 사용한다.
  - User Service:
    - `POST /api/v1/login-sessions` 로 넘어온 세션 정보를 그대로 저장 (CRUD 역할만 수행)
    - `DELETE /api/v1/login-sessions/{session_id}` 호출 시 해당 세션 도큐먼트를 찾아 삭제하고, 저장된 `jwt_token` 을 반환한다.

- **결과**
  - JWT 는 더 이상 URL, 서버 액세스 로그, Referer 등에 노출되지 않는다.
  - 세션 ID 는 짧은 TTL 과 1회성 삭제(DELETE + `find_one_and_delete`)로 관리되어, 도난되더라도 공격 가능 시간이 매우 제한된다.
  - User Service 는 인증/인가 비즈니스 로직 없이, **임시 로그인 세션 데이터 저장소** 역할에만 집중한다.
