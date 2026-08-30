"""설정 단일 트리 (pydantic-settings).

필수값이 없으면 **부팅 즉시** 실패한다. 런타임 중간에 갑자기 RuntimeError를
내지 않는다.
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
    # 4개 역할이 실제로는 Gemini 키 하나 / OpenRouter 키 하나를 그대로 복붙해
    # 썼다. 역할별 시크릿 대신 provider별 공유 키 하나로 정리한다.
    api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")


class EmbeddingLlmSettings(LlmSettings):
    model_config = _llm_config("EMBEDDING_WORKER_LLM_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "google"
    model_name: str = "gemini-embedding-001"
    api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")


class ChatLlmSettings(LlmSettings):
    model_config = _llm_config("CHATBOT_LLM_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "openrouter"
    temperature: float = 0.7
    api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")


class ChatEmbeddingSettings(LlmSettings):
    model_config = _llm_config("CHATBOT_EMBEDDING_")
    provider: Literal["google", "openai", "openrouter", "ollama"] = "google"
    model_name: str = "gemini-embedding-001"
    api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")


class RouterSettings(BaseSettings):
    """LLM 모델 라우터."""

    model_config = _BASE
    scouter_timeout_seconds: float = 20.0
    scouter_cache_ttl_seconds: int = 600
    scouter_scan_interval_hours: float = 1.0
    scouter_scan_max_retries: int = 2
    scouter_scan_concurrency: int = 2
    scouter_scan_request_delay_seconds: float = 0.3
    scouter_scan_prompt: str = "Respond with the exact text: OK"
    scouter_check_retention_days: int = 3
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
    """Mongo 잡 큐."""

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
    dead_retryable_alert_threshold: int = Field(
        default=5, alias="JOB_DEAD_RETRYABLE_ALERT_THRESHOLD"
    )

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


class EmbeddingSettings(BaseSettings):
    """청킹·임베딩."""

    model_config = _BASE
    chunk_size: int = Field(default=1000, alias="EMBEDDING_WORKER_CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, alias="EMBEDDING_WORKER_CHUNK_OVERLAP")
    embed_batch_size: int = 64
    """한 번에 임베딩 API로 보내는 청크 수. 긴 글이 요청 하나로 몰리지 않게 한다."""
    max_chunks_per_post: int = 200
    """포스트 하나의 상한. 91K자짜리 글이 벡터를 수백 개 만드는 것을 막는다."""


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
    router: RouterSettings
    jobs: JobSettings
    rss: RssSettings
    summary: SummarySettings
    embedding: EmbeddingSettings
    chat: ChatSettings

    auth_settings: AuthSettings | None = Field(default=None, exclude=True)
    """지연 로딩. 아래 `auth` 프로퍼티로 접근한다."""

    summary_llm: SummaryLlmSettings
    embedding_llm: EmbeddingLlmSettings
    chat_llm: ChatLlmSettings
    chat_embedding: ChatEmbeddingSettings

    @property
    def auth(self) -> AuthSettings:
        """OAuth·JWT 설정. **처음 쓸 때** 읽는다.

        워커는 로그인을 처리하지 않는다. 부팅 때 함께 읽으면 요약 워커가
        Google OAuth 자격증명 없이는 뜨지 못하고, 필요도 없는 프로세스에
        시크릿을 넣어야 한다.
        """
        if self.auth_settings is None:
            self.auth_settings = AuthSettings()  # pyright: ignore[reportCallIssue]
        return self.auth_settings

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
            router=RouterSettings(),
            jobs=JobSettings(),
            rss=RssSettings(),
            summary=SummarySettings(),
            embedding=EmbeddingSettings(),
            chat=ChatSettings(),
            summary_llm=SummaryLlmSettings(),
            embedding_llm=EmbeddingLlmSettings(),
            chat_llm=ChatLlmSettings(),
            chat_embedding=ChatEmbeddingSettings(),
        )


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
