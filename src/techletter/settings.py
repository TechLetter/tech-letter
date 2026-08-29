"""설정 단일 트리 (pydantic-settings).

원칙
- **시크릿 환경변수 이름은 기존 그대로다**(제약 C2). 값을 옮길 필요가 없다.
- 필수값이 없으면 **부팅 즉시** 실패한다. 현행처럼 런타임 중간에 RuntimeError를
  내지 않는다(ISSUE-023).
- 현행에 흩어져 있던 하드코딩 상수를 전부 필드로 올리되 기본값은 현행 값이다.
"""

from __future__ import annotations

import functools
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

__all__ = ["Settings", "get_settings"]

_BASE = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
    populate_by_name=True,  # 테스트에서 alias 대신 필드명으로 생성할 수 있게 한다
)


def _csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if str(v).strip()]
    return [v.strip() for v in value.split(",") if v.strip()]


class MongoSettings(BaseSettings):
    model_config = _BASE
    uri: SecretStr = Field(alias="MONGO_URI")
    db_name: str = Field(default="techletter", alias="MONGO_DB_NAME")
    server_selection_timeout_ms: int = 5000
    connect_timeout_ms: int = 5000
    socket_timeout_ms: int = 30000


class QdrantSettings(BaseSettings):
    model_config = _BASE
    host: str = Field(default="qdrant", alias="QDRANT_HOST")
    port: int = Field(default=6333, alias="QDRANT_PORT")
    collection_base: str = Field(default="tech_letter_posts", alias="QDRANT_COLLECTION_NAME")


class AuthSettings(BaseSettings):
    model_config = _BASE
    jwt_secret: SecretStr = Field(alias="JWT_SECRET")
    jwt_issuer: str = Field(default="tech-letter", alias="JWT_ISSUER")
    jwt_ttl_seconds: int = 24 * 60 * 60
    google_client_id: str = Field(alias="GOOGLE_OAUTH_CLIENT_ID")
    google_client_secret: SecretStr = Field(alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_redirect_url: str = Field(alias="GOOGLE_OAUTH_REDIRECT_URL")
    login_success_redirect_url: str = Field(alias="AUTH_LOGIN_SUCCESS_REDIRECT_URL")
    login_session_ttl_seconds: int = 60
    oauth_state_ttl_seconds: int = 300
    cookie_secure: bool = Field(default=True, alias="AUTH_COOKIE_SECURE")


def _llm_config(prefix: str) -> SettingsConfigDict:
    return SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        env_prefix=prefix,
    )


class LlmSettings(BaseSettings):
    """provider별 LLM 설정. 용도별 서브클래스가 env prefix를 지정한다.

    필드명이 그대로 기존 환경변수명이 된다:
    `SUMMARY_WORKER_LLM_` + `MODEL_NAME` → `SUMMARY_WORKER_LLM_MODEL_NAME`.
    """

    model_config = _BASE
    provider: Literal["google", "openai", "openrouter", "ollama"] = "google"
    model_name: str = ""
    api_key: SecretStr | None = None
    base_url: str | None = None
    temperature: float = 0.3
    max_retries: int = 0
    timeout_seconds: int = 120


class SummaryLlmSettings(LlmSettings):
    model_config = _llm_config("SUMMARY_WORKER_LLM_")


class EmbeddingLlmSettings(LlmSettings):
    model_config = _llm_config("EMBEDDING_WORKER_LLM_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "google"
    model_name: str = "gemini-embedding-001"


class ChatLlmSettings(LlmSettings):
    model_config = _llm_config("CHATBOT_LLM_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "openrouter"
    temperature: float = 0.7


class ChatEmbeddingSettings(LlmSettings):
    model_config = _llm_config("CHATBOT_EMBEDDING_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "google"
    model_name: str = "gemini-embedding-001"


class RouterSettings(BaseSettings):
    """LLM 모델 라우터 (ADR-0008)."""

    model_config = _BASE
    scouter_base_url: str = Field(
        default="http://openrouter-scouter:8000", alias="SCOUTER_BASE_URL"
    )
    scouter_timeout_seconds: float = 3.0
    scouter_cache_ttl_seconds: int = 600
    min_uptime_24h: float = 90.0
    max_model_attempts: int = 3
    min_success_rate: float = Field(default=0.6, alias="LLM_MIN_SUCCESS_RATE")
    min_attempts_for_demotion: int = 10
    quota_reset_utc_hour: int = Field(default=7, alias="LLM_QUOTA_RESET_UTC_HOUR")
    summary_daily_budget: int = Field(default=20, alias="SUMMARY_DAILY_BUDGET")
    summary_preference: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="SUMMARY_MODEL_PREFERENCE"
    )
    chat_preference: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="CHAT_MODEL_PREFERENCE"
    )
    planner_preference: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="CHAT_PLANNER_MODEL_PREFERENCE"
    )
    static_fallback: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="LLM_STATIC_FALLBACK_MODELS"
    )
    chat_gemini_fallback: bool = Field(default=True, alias="CHAT_GEMINI_FALLBACK")

    @field_validator(
        "summary_preference",
        "chat_preference",
        "planner_preference",
        "static_fallback",
        mode="before",
    )
    @classmethod
    def _split(cls, v: str | list[str] | None) -> list[str]:
        return _csv(v)


class JobSettings(BaseSettings):
    """Mongo 잡 큐 (ADR-0004)."""

    model_config = _BASE
    poll_interval_seconds: float = Field(default=2.0, alias="JOB_POLL_INTERVAL_SECONDS")
    idle_backoff_seconds: float = 10.0
    lock_timeout_minutes: int = Field(default=30, alias="JOB_LOCK_TIMEOUT_MINUTES")
    summary_lock_timeout_minutes: int = 60
    max_attempt: int = Field(default=5, alias="JOB_MAX_ATTEMPT")
    backoff_minutes: Annotated[list[int], NoDecode] = Field(
        default=[5, 30, 120, 480, 1440], alias="JOB_BACKOFF_MINUTES"
    )
    done_ttl_days: int = 14
    quota_max_wait_hours: int = 30

    @field_validator("backoff_minutes", mode="before")
    @classmethod
    def _ints(cls, v: str | list[int] | None) -> list[int]:
        if isinstance(v, str):
            return [int(x) for x in _csv(v)]
        return list(v) if v else [5, 30, 120, 480, 1440]


class RssSettings(BaseSettings):
    model_config = _BASE
    interval_seconds: int = 30 * 60
    batch_size: int = Field(default=10, alias="CONTENT_BLOG_FETCH_BATCH_SIZE")
    request_timeout_seconds: int = 30
    tls_insecure_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="RSS_TLS_INSECURE_HOSTS"
    )
    auto_disable_after_failures: int = 48

    @field_validator("tls_insecure_hosts", mode="before")
    @classmethod
    def _split(cls, v: str | list[str] | None) -> list[str]:
        return _csv(v)


class SummarySettings(BaseSettings):
    model_config = _BASE
    renderer_strategy: Literal["playwright", "scraperapi"] = Field(
        default="playwright", alias="RENDERER_STRATEGY"
    )
    scraperapi_key: SecretStr | None = Field(default=None, alias="SCRAPERAPI_KEY")
    max_input_chars: int = Field(default=12000, alias="SUMMARY_MAX_INPUT_CHARS")
    max_render_attempts: int = 3
    render_timeout_seconds: int = 30
    max_thumbnail_candidates: int = 10
    summary_target_chars: int = 200
    summary_tolerance_chars: int = 20
    max_tags: int = 7


class ChatSettings(BaseSettings):
    model_config = _BASE
    rag_top_k: int = Field(default=5, alias="CHATBOT_RAG_TOP_K")
    rag_score_threshold: float = Field(default=0.5, alias="CHATBOT_RAG_SCORE_THRESHOLD")
    history_limit: int = 60
    memory_recent_messages: int = 8
    memory_max_message_chars: int = 1200
    memory_max_summary_chars: int = 1800
    compression_min_messages: int = Field(default=12, alias="CHAT_CONTEXT_COMPRESSION_MIN_MESSAGES")
    compression_batch_size: int = Field(default=6, alias="CHAT_CONTEXT_COMPRESSION_BATCH_SIZE")
    credits_per_message: int = 1
    daily_credit_grant: int = 10


class Settings(BaseSettings):
    model_config = _BASE

    service_name: str = Field(default="techletter", alias="SERVICE_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_port: int = Field(default=8080, alias="API_PORT")
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="CORS_ALLOWED_ORIGINS"
    )

    mongo: MongoSettings
    qdrant: QdrantSettings
    auth: AuthSettings
    router: RouterSettings
    jobs: JobSettings
    rss: RssSettings
    summary: SummarySettings
    chat: ChatSettings

    summary_llm: SummaryLlmSettings
    embedding_llm: EmbeddingLlmSettings
    chat_llm: ChatLlmSettings
    chat_embedding: ChatEmbeddingSettings

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split(cls, v: str | list[str] | None) -> list[str]:
        return _csv(v)

    @classmethod
    def load(cls) -> Settings:
        """중첩 모델을 각자의 env prefix로 조립한다.

        pydantic-settings의 nested delimiter 대신 명시적으로 조립한다 —
        기존 변수명(`SUMMARY_WORKER_LLM_MODEL_NAME` 등)을 그대로 써야 하기 때문이다.
        """
        return cls(
            mongo=MongoSettings(),  # pyright: ignore[reportCallIssue]
            qdrant=QdrantSettings(),
            auth=AuthSettings(),  # pyright: ignore[reportCallIssue]
            router=RouterSettings(),
            jobs=JobSettings(),
            rss=RssSettings(),
            summary=SummarySettings(),
            chat=ChatSettings(),
            summary_llm=SummaryLlmSettings(),
            embedding_llm=EmbeddingLlmSettings(),
            chat_llm=ChatLlmSettings(),
            chat_embedding=ChatEmbeddingSettings(),
        )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
