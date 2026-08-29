"""MongoDB 비동기 클라이언트 수명주기.

현행 문제(09 §3.2): 동기 pymongo를 async 라우트에서 호출해 이벤트 루프를
막았고, 타임아웃·`tz_aware`가 설정돼 있지 않았으며, 클라이언트 생성 함수가
"indexes ensured"라는 거짓 로그를 남겼다(인덱스를 만들지 않았다).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pymongo import AsyncMongoClient

from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.settings import MongoSettings

__all__ = ["MongoConnection", "create_client"]

logger = get_logger(__name__)


def create_client(settings: MongoSettings) -> AsyncMongoClient:
    """타임아웃과 tz_aware를 명시한 클라이언트를 만든다.

    `tz_aware=True`가 없으면 Mongo에서 읽은 datetime이 naive로 올라와
    aware/naive가 코드 전반에 섞인다.
    """
    return AsyncMongoClient(
        settings.uri.get_secret_value(),
        tz_aware=True,
        serverSelectionTimeoutMS=settings.server_selection_timeout_ms,
        connectTimeoutMS=settings.connect_timeout_ms,
        socketTimeoutMS=settings.socket_timeout_ms,
    )


class MongoConnection:
    """앱/워커 수명 동안 하나만 두는 연결."""

    def __init__(self, settings: MongoSettings) -> None:
        self._settings = settings
        self._client: AsyncMongoClient | None = None

    @property
    def client(self) -> AsyncMongoClient:
        if self._client is None:
            msg = "Mongo 연결이 열려 있지 않다. connect()를 먼저 호출한다."
            raise RuntimeError(msg)
        return self._client

    @property
    def db(self) -> AsyncDatabase:
        return self.client[self._settings.db_name]

    async def connect(self, *, ping: bool = True) -> AsyncDatabase:
        if self._client is None:
            self._client = create_client(self._settings)
        if ping:
            await self._client.admin.command("ping")
            logger.info("mongo connected", extra={"db": self._settings.db_name})
        return self.db

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("mongo closed")

    async def healthy(self) -> bool:
        try:
            await self.client.admin.command("ping")
        except Exception:
            return False
        return True
