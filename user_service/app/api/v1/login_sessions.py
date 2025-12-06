from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone

from ..schemas.login_sessions import (
    LoginSessionCreateRequest,
    LoginSessionCreateResponse,
    LoginSessionDeleteResponse,
)
from ...models.login_session import LoginSession
from ...services.login_sessions_service import (
    LoginSessionsService,
    get_login_sessions_service,
)


router = APIRouter()


@router.post(
    "",
    response_model=LoginSessionCreateResponse,
    summary="로그인 세션 생성 (Gateway 전용)",
)
async def create_login_session(
    body: LoginSessionCreateRequest,
    service: LoginSessionsService = Depends(get_login_sessions_service),
) -> LoginSessionCreateResponse:
    now = datetime.now(timezone.utc)
    session = LoginSession(
        session_id=body.session_id,
        jwt_token=body.jwt_token,
        expires_at=body.expires_at,
        created_at=now,
        updated_at=now,
    )
    session = service.create(session=session)
    return LoginSessionCreateResponse(session_id=session.session_id)


@router.delete(
    "/{session_id}",
    response_model=LoginSessionDeleteResponse,
    summary="로그인 세션 삭제 (Gateway 전용)",
)
async def delete_login_session(
    session_id: str,
    service: LoginSessionsService = Depends(get_login_sessions_service),
) -> LoginSessionDeleteResponse:
    session = service.delete_session(session_id=session_id)
    if session is None:
        # 세션이 없거나 만료된 경우
        raise HTTPException(
            status_code=400,
            detail="login session not found or expired",
        )

    return LoginSessionDeleteResponse(jwt_token=session.jwt_token)
