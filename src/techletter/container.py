"""의존성 조립.

프로세스 하나가 API도 워커도 될 수 있으므로 조립을 한 곳에 모은다.
연결(Mongo, Qdrant, HTTP)은 **앱 수명 동안 하나**만 만든다.

무거운 의존(langchain, playwright)은 실제로 필요할 때 올린다. API 프로세스가
요약용 브라우저를 import할 이유가 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from techletter.core.db.indexes import ensure_indexes
from techletter.core.db.mongo import MongoConnection
from techletter.core.http import HttpClients
from techletter.core.jobs import JobQueue, RetryPolicy
from techletter.core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from pymongo.asynchronous.database import AsyncDatabase

    from techletter.chat.agent import ChatAgent
    from techletter.chat.sessions import ChatSessionService
    from techletter.chat.suggested_questions import SuggestedQuestionService
    from techletter.chat.use_case import ChatUseCase
    from techletter.content.filters import FiltersService
    from techletter.content.repositories import BlogRepository, PostRepository
    from techletter.content.service import BlogService, PostService
    from techletter.content.trends import TrendsService
    from techletter.core.db.qdrant import VectorStore
    from techletter.core.llm.chat import LlmGateway
    from techletter.core.llm.stats import ModelStatsStore
    from techletter.explainer.repository import ExplainerRepository
    from techletter.search.service import SearchService
    from techletter.search.summary import SearchSummaryService
    from techletter.settings import Settings
    from techletter.users.auth_service import AuthService
    from techletter.users.credits import CreditService
    from techletter.users.repositories import BookmarkRepository
    from techletter.users.service import UserService

__all__ = ["Container"]

logger = get_logger(__name__)


@dataclass
class Container:
    """열려 있는 연결과 조립된 서비스.

    `open()`으로 만들고 `close()`로 닫는다. FastAPI 수명주기와 워커가 같은
    것을 쓴다.
    """

    settings: Settings
    mongo: MongoConnection
    http: HttpClients

    _db: AsyncDatabase | None = None
    _vector_store: VectorStore | None = None
    _chat: ChatUseCase | None = None
    _chat_agent: ChatAgent | None = None
    _search: SearchService | None = None
    _search_summary: SearchSummaryService | None = None

    # ── 수명주기 ───────────────────────────────────────────────────
    @classmethod
    async def open(cls, settings: Settings, *, create_indexes: bool = True) -> Container:
        # `register_indexes`를 호출하는 모듈만 import해야 인덱스 레지스트리가 채워진다.
        import techletter.chat.repositories  # noqa: PLC0415
        import techletter.content.repositories  # noqa: PLC0415
        import techletter.core.jobs.queue  # noqa: PLC0415
        import techletter.core.llm.model_events  # noqa: PLC0415
        import techletter.core.llm.model_history  # noqa: PLC0415
        import techletter.core.llm.model_scan  # noqa: PLC0415
        import techletter.core.llm.stats  # noqa: PLC0415
        import techletter.explainer.repository  # noqa: PLC0415
        import techletter.search.summary  # noqa: PLC0415
        import techletter.users.repositories  # noqa: F401, PLC0415

        mongo = MongoConnection(settings.mongo)
        db = await mongo.connect()
        container = cls(
            settings=settings,
            mongo=mongo,
            http=HttpClients(timeout=settings.rss.request_timeout_seconds),
        )
        container._db = db
        if create_indexes:
            # 부팅 때 한 번만 실행한다.
            await ensure_indexes(db)
        return container

    async def close(self) -> None:
        if self._vector_store is not None:
            await self._vector_store.close()
            self._vector_store = None
        await self.http.aclose()
        await self.mongo.close()

    @property
    def db(self) -> AsyncDatabase:
        if self._db is None:
            msg = "Container가 열려 있지 않다. open()을 먼저 호출한다."
            raise RuntimeError(msg)
        return self._db

    # ── 저장소 ─────────────────────────────────────────────────────
    @property
    def posts(self) -> PostRepository:
        from techletter.content.repositories import PostRepository  # noqa: PLC0415

        return PostRepository(self.db)

    @property
    def blogs(self) -> BlogRepository:
        from techletter.content.repositories import BlogRepository  # noqa: PLC0415

        return BlogRepository(self.db)

    @property
    def bookmarks(self) -> BookmarkRepository:
        from techletter.users.repositories import BookmarkRepository  # noqa: PLC0415

        return BookmarkRepository(self.db)

    @property
    def queue(self) -> JobQueue:
        return JobQueue(
            self.db,
            self.settings.jobs,
            RetryPolicy(
                self.settings.jobs,
                quota_reset_utc_hour=self.settings.router.quota_reset_utc_hour,
            ),
        )

    @property
    def explainers(self) -> ExplainerRepository:
        from techletter.explainer.repository import ExplainerRepository  # noqa: PLC0415

        return ExplainerRepository(self.db)

    @property
    def model_stats(self) -> ModelStatsStore:
        from techletter.core.llm.stats import ModelStatsStore  # noqa: PLC0415

        return ModelStatsStore(self.db, self.settings.router)

    # ── 서비스 ─────────────────────────────────────────────────────
    @property
    def credits(self) -> CreditService:
        from techletter.users.credits import CreditService  # noqa: PLC0415
        from techletter.users.repositories import (  # noqa: PLC0415
            CreditRepository,
            CreditTransactionRepository,
            IdentityPolicyRepository,
        )

        return CreditService(
            CreditRepository(self.db),
            CreditTransactionRepository(self.db),
            IdentityPolicyRepository(self.db),
            daily_credit_grant=self.settings.chat.daily_credit_grant,
        )

    @property
    def users(self) -> UserService:
        from techletter.users.repositories import UserRepository  # noqa: PLC0415
        from techletter.users.service import UserService  # noqa: PLC0415

        return UserService(UserRepository(self.db), self.credits, self.bookmarks)

    @property
    def auth(self) -> AuthService:
        from techletter.users.auth_service import AuthService  # noqa: PLC0415
        from techletter.users.repositories import LoginSessionRepository  # noqa: PLC0415

        return AuthService(
            self.settings.auth,
            self.users,
            LoginSessionRepository(self.db),
            self.http.get(),
        )

    @property
    def post_service(self) -> PostService:
        from techletter.content.service import PostService  # noqa: PLC0415

        return PostService(self.posts, self.blogs, self.queue)

    @property
    def blog_service(self) -> BlogService:
        from techletter.content.service import BlogService  # noqa: PLC0415

        return BlogService(self.blogs, self.posts, self.queue)

    @property
    def filters(self) -> FiltersService:
        from techletter.content.filters import FiltersService  # noqa: PLC0415

        return FiltersService(self.posts)

    @property
    def trends(self) -> TrendsService:
        from techletter.content.trends import TrendsService  # noqa: PLC0415

        return TrendsService(self.posts)

    @property
    def sessions(self) -> ChatSessionService:
        from techletter.chat.repositories import ChatSessionRepository  # noqa: PLC0415
        from techletter.chat.sessions import ChatSessionService  # noqa: PLC0415

        return ChatSessionService(ChatSessionRepository(self.db), self.settings.chat)

    @property
    def suggested_questions(self) -> SuggestedQuestionService:
        from techletter.chat.repositories import SuggestedQuestionRepository  # noqa: PLC0415
        from techletter.chat.suggested_questions import SuggestedQuestionService  # noqa: PLC0415

        return SuggestedQuestionService(SuggestedQuestionRepository(self.db))

    @property
    def vector_store(self) -> VectorStore:
        """Qdrant 연결은 하나만 만들어 재사용한다."""
        if self._vector_store is None:
            from techletter.core.db.qdrant import VectorStore  # noqa: PLC0415

            self._vector_store = VectorStore(self.settings.qdrant)
        return self._vector_store

    @property
    def search(self) -> SearchService:
        """질의 벡터 캐시를 요청 사이에 유지해야 해서 한 번만 만든다."""
        if self._search is None:
            from techletter.core.llm.embeddings import LangChainEmbedder  # noqa: PLC0415
            from techletter.search.service import SearchService  # noqa: PLC0415

            self._search = SearchService(
                store=self.vector_store,
                posts=self.posts,
                embedder=LangChainEmbedder(self.settings.embedding_llm),
                embedding_model=self.settings.embedding_llm.model_name,
                settings=self.settings.search,
            )
        return self._search

    @property
    def chat(self) -> ChatUseCase:
        """채팅은 조립 비용이 커서(LLM 클라이언트, 그래프 컴파일) 한 번만 만든다."""
        if self._chat is None:
            self._chat = self._build_chat()
        return self._chat

    @property
    def chat_agent(self) -> ChatAgent:
        """챗봇과 검색 AI 요약이 같은 에이전트를 쓴다."""
        if self._chat_agent is None:
            self._chat_agent = self._build_chat_agent()
        return self._chat_agent

    @property
    def search_summary(self) -> SearchSummaryService:
        """진행 중인 요약을 요청 사이에 나눠 써야 해서 한 번만 만든다."""
        if self._search_summary is None:
            from techletter.search.summary import SearchSummaryService  # noqa: PLC0415

            self._search_summary = SearchSummaryService(self.db, self.chat_agent, self.sessions)
        return self._search_summary

    def _chat_llm(self) -> LlmGateway:
        from techletter.core.llm.chat import LangChainChatClient, LlmGateway  # noqa: PLC0415
        from techletter.core.llm.router import ModelRouter  # noqa: PLC0415
        from techletter.core.llm.scouter import ScouterClient  # noqa: PLC0415

        router = ModelRouter(
            self.settings.router,
            ScouterClient(self.settings.router, self.db),
            stats=self.model_stats,
        )
        return LlmGateway(router, LangChainChatClient(self.settings.chat_llm))

    def _build_chat_agent(self) -> ChatAgent:
        from techletter.chat.agent import (  # noqa: PLC0415
            AnswerGenerator,
            ChatAgent,
            EvidenceBuilder,
            PostLookupTool,
        )

        return ChatAgent(
            evidence=EvidenceBuilder(
                search=self.search,
                store=self.vector_store,
                posts=self.posts,
                embedding_model=self.settings.embedding_llm.model_name,
                max_posts=self.settings.chat.rag_top_k,
                chunks_per_post=self.settings.chat.rag_chunks_per_post,
                max_chunk_chars=self.settings.chat.rag_chunk_chars,
            ),
            posts=PostLookupTool(self.posts),
            answers=AnswerGenerator(self._chat_llm()),
            blogs=self.blogs,
        )

    def _build_chat(self) -> ChatUseCase:
        from techletter.chat.memory import MemoryBuilder  # noqa: PLC0415
        from techletter.chat.use_case import ChatUseCase  # noqa: PLC0415

        return ChatUseCase(
            sessions=self.sessions,
            credits=self.credits,
            memory=MemoryBuilder(self.settings.chat),
            agent=self.chat_agent,
            queue=self.queue,
            settings=self.settings.chat,
        )
