from __future__ import annotations

from fastapi import Depends
from pymongo.database import Database

from common.mongo.client import get_database

from ..models.login_session import LoginSession
from ..repositories.login_session_repository import LoginSessionRepository
from ..repositories.interfaces import LoginSessionRepositoryInterface


class LoginSessionsService:
    """로그인 세션 데이터 생성/삭제를 담당하는 서비스."""

    def __init__(self, repo: LoginSessionRepositoryInterface) -> None:
        self._repo = repo

    def create(self, session: LoginSession) -> LoginSession:
        return self._repo.create(session)

    def delete_session(self, session_id: str) -> LoginSession | None:
        return self._repo.delete_by_session_id(session_id)


def get_login_session_repository(
    db: Database = Depends(get_database),
) -> LoginSessionRepositoryInterface:
    return LoginSessionRepository(db)


def get_login_sessions_service(
    repo: LoginSessionRepositoryInterface = Depends(get_login_session_repository),
) -> LoginSessionsService:
    return LoginSessionsService(repo)
