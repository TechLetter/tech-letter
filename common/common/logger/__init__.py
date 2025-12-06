import json
import logging
import os
import sys


def setup_logger(name: str = "tech-letter", level: str | None = None) -> logging.Logger:
    """애플리케이션 전역 로거를 설정하고 반환한다.

    Args:
        name: 로거 이름 (기본값: tech-letter)
        level: 로그 레벨 (기본값: None -> 환경변수 LOG_LEVEL 또는 INFO 사용)

    Returns:
        설정된 logging.Logger 인스턴스
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    # 문자열 레벨을 logging 상수(int)로 변환
    log_level = getattr(logging, level.upper(), logging.INFO)

    service_name = os.getenv("SERVICE_NAME", name)
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)

    # 이미 핸들러가 있다면 제거 (중복 출력 방지)
    if logger.handlers:
        logger.handlers.clear()

    # 콘솔 핸들러 생성 (항상 JSON 포맷 사용)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    formatter: logging.Formatter = JsonFormatter()
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # 루트 로거에도 동일한 설정 적용 (라이브러리 로그 등도 제어하기 위함)
    # 다만, 너무 시끄러울 수 있으므로 루트 로거는 기본적으로 INFO 이상만 출력하도록 조정 가능
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(handler)
        root_logger.setLevel(log_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거를 가져온다."""
    return logging.getLogger(name)


class JsonFormatter(logging.Formatter):
    """구조화 로그 수집을 위한 간단한 JSON 포맷터.

    - timestamp, level, logger, message 필드를 기본으로 포함한다.
    - 예외 정보가 있으면 exc_info 필드에 문자열로 추가한다.
    """

    def __init__(self) -> None:
        super().__init__(datefmt="%Y-%m-%dT%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        log_record: dict[str, object] = {
            "datetime": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # request_id, span_id 는 extra 로 넘어온 값을 우선 사용한다.
        # HTTP 관련 메타데이터(method, path, query 등)를 포함한 공통 extra 필드를 한번에 처리한다.
        extra_keys = (
            "request_id",
            "span_id",
            "method",
            "path",
            "query_params",
            "status",
            "body",
            "duration",
        )
        for key in extra_keys:
            if hasattr(record, key):
                log_record[key] = getattr(record, key)

        # service_name 은 extra 의 service_name 이나 SERVICE_NAME 환경변수를 사용한다.
        service_name = getattr(record, "service_name", None) or os.getenv(
            "SERVICE_NAME"
        )
        if service_name:
            log_record["service_name"] = service_name

        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)
