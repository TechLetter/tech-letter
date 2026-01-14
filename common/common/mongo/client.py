from __future__ import annotations

import logging
import threading
from typing import Optional, cast

from pymongo import MongoClient
from pymongo.database import Database

from .config import get_mongo_db_name, get_mongo_uri


logger = logging.getLogger(__name__)


_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_lock = threading.Lock()


def get_client() -> MongoClient:
    """전역 MongoClient 싱글톤을 반환한다.

    - MONGO_URI 에서 URI 를 읽어온다.
    - ping 으로 연결을 검증한다.
    - URI 에 기본 데이터베이스가 포함되어 있지 않으면 에러를 발생시킨다.
    - MONGO_URI 에서 URI 를 읽어온다.
    - ping 으로 연결을 검증한다.
    - URI 에 기본 데이터베이스가 포함되어 있지 않으면 에러를 발생시킨다.
    """

    global _client, _db

    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client

        uri = get_mongo_uri()
        client = MongoClient(uri)

        # 연결 확인 (Go 구현의 Ping 과 동일한 목적)
        try:
            client.admin.command("ping")
        except Exception as exc:  # noqa: BLE001
            client.close()
            raise RuntimeError(f"failed to connect to MongoDB: {exc}") from exc

        # 사용할 DB 이름 결정: MONGO_DB_NAME 우선, 없으면 URI의 기본 DB 사용
        db_name = get_mongo_db_name()
        try:
            if db_name:
                db = client[db_name]
            else:
                db = client.get_default_database()
        except Exception as exc:  # noqa: BLE001
            client.close()
            raise RuntimeError(
                "MongoDB database name must be specified via MONGO_DB_NAME or in MONGO_URI (mongodb://.../db_name)",
            ) from exc

        _client = client
        _db = db

        _client = client
        _db = db

        safe_db = cast(Database, _db)
        logger.info("MongoDB connected and indexes ensured (db=%s)", safe_db.name)
        return _client


def get_database() -> Database:
    """전역 기본 Database 객체를 반환한다."""

    global _db

    if _db is None:
        get_client()
    assert (
        _db is not None
    )  # get_client 에서 _db 를 초기화하지 못했다면 예외가 이미 발생했어야 한다.
    return _db
