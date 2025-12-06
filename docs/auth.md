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
5. 성공 시 `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>?token=<JWT>` 로 프론트로 리다이렉트한다.
6. 실패 시 `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>` (쿼리 파라미터 없이) 로 리다이렉트한다.
7. 프론트는 `/login/success` 페이지에서 `?token=<JWT>` 를 읽어 localStorage 등에 저장하고,
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
- **리다이렉트 규칙**
  - **성공:** `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>?token=<JWT>`
  - **실패:** `302 Location: <AUTH_LOGIN_SUCCESS_REDIRECT_URL>` (쿼리 파라미터 없음)

프론트는 `/login/success` 페이지에서 `token` 유무로 성공/실패를 판별한다.

---

### 2.3 `GET /api/v1/users/profile`

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

프론트는 `/login/success?token=<JWT>` 로 전달된 토큰을 그대로 저장하고,
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

> `/login/success?token=<JWT>` 쿼리로 넘어온 액세스 토큰을 localStorage 에 저장하고,
> 이후 모든 API 호출에서 `Authorization: Bearer <JWT>` 헤더를 사용해
> `/api/v1/users/profile` 로 현재 유저 정보를 가져온다.

- 로그인 시작: `GET /api/v1/auth/google/login` 으로 페이지 이동
- 콜백/토큰 생성: Gateway 가 처리 (프론트 직접 호출 없음)
- 프로필 조회: `GET /api/v1/users/profile` + `Authorization: Bearer <JWT>`
