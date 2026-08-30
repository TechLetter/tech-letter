"""Google OAuth 로그인 흐름.

1. `/auth/google/login` → state 쿠키(300초) 설정 후 Google로 302
2. Google → `/auth/google/callback?state&code`
3. state 검증 → code 교환 → userinfo → 유저 upsert → JWT 발급
   → 로그인 세션(60초) 저장 → `{FRONT}/login/success?session=<id>`로 302
4. 프론트가 `POST /auth/token`으로 JWT를 교환

**모든 실패는 쿼리 없는 302다.** JSON 에러를 내지 않는다 — 프론트가 그 동작에
기대고 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from techletter.core.errors import SessionExpiredError
from techletter.core.ids import random_token
from techletter.core.logging import get_logger
from techletter.core.security import issue_token
from techletter.users.service import OAuthProfile

if TYPE_CHECKING:  # pragma: no cover
    from techletter.settings import AuthSettings
    from techletter.users.credits import CreditService
    from techletter.users.repositories import LoginSessionRepository
    from techletter.users.service import UserService

__all__ = ["OAUTH_STATE_COOKIE", "AuthService", "GoogleOAuthError"]

logger = get_logger(__name__)

OAUTH_STATE_COOKIE = "oauth_state"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SCOPES = "openid email profile"
PROVIDER = "google"


class GoogleOAuthError(Exception):
    """OAuth 흐름 실패. 호출자는 쿼리 없는 302로 응답한다."""


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorize_url: str
    state: str


class AuthService:
    def __init__(
        self,
        settings: AuthSettings,
        users: UserService,
        credits: CreditService,
        sessions: LoginSessionRepository,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._users = users
        self._credits = credits
        self._sessions = sessions
        self._client = client

    def start_login(self) -> LoginStart:
        state = random_token(16)
        params = {
            "client_id": self._settings.google_client_id,
            "redirect_uri": self._settings.google_redirect_url,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "access_type": "online",
        }
        return LoginStart(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state)

    async def handle_callback(self, code: str, state: str, cookie_state: str | None) -> str:
        """콜백을 처리하고 프론트로 보낼 리다이렉트 URL을 준다.

        실패하면 `GoogleOAuthError`. 호출자가 쿼리 없는 리다이렉트로 바꾼다.
        """
        if not state or not cookie_state or state != cookie_state:
            msg = "state mismatch"
            raise GoogleOAuthError(msg)
        if not code:
            msg = "missing code"
            raise GoogleOAuthError(msg)

        profile = await self._fetch_profile(code)
        user = await self._users.upsert_from_oauth(profile)
        token = issue_token(self._settings, user.user_code, user.role)

        session_id = random_token(16)
        await self._sessions.create(session_id, token, self._settings.login_session_ttl_seconds)

        # 크레딧 지급 실패가 로그인을 막지 않는다.
        try:
            await self._credits.grant_daily(user.user_code, profile.provider, profile.provider_sub)
        except Exception:
            logger.warning("daily credit grant failed", extra={"user_code": user.user_code})

        return self._redirect_with_session(session_id)

    async def exchange_session(self, session_id: str) -> str:
        """1회용 세션을 JWT로 교환한다. 빈 문자열·공백도 400으로 처리한다."""
        token = await self._sessions.consume(session_id.strip()) if session_id.strip() else None
        if not token:
            raise SessionExpiredError
        return token

    def failure_redirect(self) -> str:
        """실패 시 목적지. 쿼리를 붙이지 않는다."""
        return self._settings.login_success_redirect_url

    def _redirect_with_session(self, session_id: str) -> str:
        """`?session=`을 붙인다. 기존 쿼리가 있어도 깨지지 않게 조립한다."""
        parts = urlparse(self._settings.login_success_redirect_url)
        query = f"{parts.query}&session={session_id}" if parts.query else f"session={session_id}"
        return urlunparse(parts._replace(query=query))

    async def _fetch_profile(self, code: str) -> OAuthProfile:
        data = {
            "code": code,
            "client_id": self._settings.google_client_id,
            "client_secret": self._settings.google_client_secret.get_secret_value(),
            "redirect_uri": self._settings.google_redirect_url,
            "grant_type": "authorization_code",
        }
        try:
            if self._client is not None:
                token_response = await self._client.post(GOOGLE_TOKEN_URL, data=data)
                token_response.raise_for_status()
                access_token = token_response.json().get("access_token")
                user_response = await self._client.get(
                    GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
                )
                user_response.raise_for_status()
                payload = user_response.json()
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    token_response = await client.post(GOOGLE_TOKEN_URL, data=data)
                    token_response.raise_for_status()
                    access_token = token_response.json().get("access_token")
                    user_response = await client.get(
                        GOOGLE_USERINFO_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    user_response.raise_for_status()
                    payload = user_response.json()
        except httpx.HTTPError as exc:
            msg = f"google oauth failed: {exc}"
            raise GoogleOAuthError(msg) from exc

        subject = payload.get("sub")
        if not subject:
            msg = "google userinfo missing sub"
            raise GoogleOAuthError(msg)
        return OAuthProfile(
            provider=PROVIDER,
            provider_sub=str(subject),
            email=payload.get("email"),
            name=payload.get("name"),
            profile_image=payload.get("picture"),
        )
