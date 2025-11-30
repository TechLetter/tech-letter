from __future__ import annotations

import os


MONGO_URI_ENV = "MONGO_URI"
MONGO_DB_NAME_ENV = "MONGO_DB_NAME"


def get_mongo_uri() -> str:
    """MongoDB 연결에 사용할 URI를 반환한다.

    Go `db.Init` 와 마찬가지로 환경 변수에서만 읽고, 설정되지 않은 경우에는
    애플리케이션이 즉시 실패하도록 RuntimeError를 발생시킨다.
    """

    value = os.getenv(MONGO_URI_ENV)
    if not value:
        raise RuntimeError(
            f"{MONGO_URI_ENV} environment variable is required for MongoDB",
        )
    return value


def get_mongo_db_name() -> str | None:
    """MongoDB에서 사용할 기본 데이터베이스 이름을 반환한다.

    - MONGO_DB_NAME 이 설정되어 있으면 해당 값을 사용한다.
    - 설정되어 있지 않으면 None 을 반환하고, 클라이언트는 URI의 기본 DB를 사용한다.
    """

    value = os.getenv(MONGO_DB_NAME_ENV, "").strip()
    return value or None
