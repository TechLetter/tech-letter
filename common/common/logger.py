import logging
import os
import sys
from typing import Any

# Go의 InitLogger/NewLogger와 유사한 설정을 제공하는 로깅 설정 모듈


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

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # 이미 핸들러가 있다면 제거 (중복 출력 방지)
    if logger.handlers:
        logger.handlers.clear()

    # 콘솔 핸들러 생성
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # 포맷 설정: [시간] [레벨] [모듈명] 메시지
    # Go의 gookit/slog 기본 포맷과 유사하게 구성
    # 예: 2025-12-01 23:15:05,123 [INFO] [summary_worker.app.main] handling PostCreatedEvent...
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
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
