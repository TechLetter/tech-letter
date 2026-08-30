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

    from techletter.chat.sessions import ChatSessionService
    from techletter.chat.suggested_questions import SuggestedQuestionService
    from techletter.chat.use_case import ChatUseCase
    from techletter.content.filters import FiltersService
    from techletter.content.repositories import BlogRepository, PostRepository
    from techletter.content.service import BlogService, PostService
    from techletter.content.trends import TrendsService
    from techletter.core.db.qdrant import VectorStore
    from techletter.core.llm.stats import ModelStatsStore
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

    # ── 수명주기 ───────────────────────────────────────────────────
    @classmethod
    async def open(cls, settings: Settings, *, create_indexes: bool = True) -> Container:
        # 저장소 모듈을 먼저 import해야 인덱스 레지스트리가 채워진다.
        import techletter.chat.repositories  # noqa: PLC0415
        import techletter.content.repositories  # noqa: PLC0415
        import techletter.core.jobs.queue  # noqa: PLC0415
        import techletter.core.llm.stats  # noqa: PLC0415
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
            self.credits,
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
    def chat(self) -> ChatUseCase:
        """채팅은 조립 비용이 커서(LLM 클라이언트, 그래프 컴파일) 한 번만 만든다."""
        if self._chat is None:
            self._chat = self._build_chat()
        return self._chat

    def _build_chat(self) -> ChatUseCase:
        from techletter.chat.agent import (  # noqa: PLC0415
            AnswerGenerator,
            ChatAgent,
            PostLookupTool,
            QueryPlanner,
            VectorSearchTool,
        )
        from techletter.chat.memory import MemoryBuilder  # noqa: PLC0415
        from techletter.chat.use_case import ChatUseCase  # noqa: PLC0415
        from techletter.core.llm.chat import LangChainChatClient, LlmGateway  # noqa: PLC0415
        from techletter.core.llm.embeddings import LangChainEmbedder  # noqa: PLC0415
        from techletter.core.llm.router import ModelRouter  # noqa: PLC0415
        from techletter.core.llm.scouter import ScouterClient  # noqa: PLC0415

        router = ModelRouter(
            self.settings.router,
            ScouterClient(self.settings.router, self.http.get()),
            stats=self.model_stats,
        )
        llm = LlmGateway(router, LangChainChatClient(self.settings.chat_llm))
        agent = ChatAgent(
            planner=QueryPlanner(llm),
            posts=PostLookupTool(self.posts),
            search=VectorSearchTool(
                embedder=LangChainEmbedder(self.settings.chat_embedding),
                store=self.vector_store,
                embedding_model=self.settings.chat_embedding.model_name,
                top_k=self.settings.chat.rag_top_k,
                score_threshold=self.settings.chat.rag_score_threshold,
            ),
            answers=AnswerGenerator(llm),
        )
        return ChatUseCase(
            sessions=self.sessions,
            credits=self.credits,
            memory=MemoryBuilder(llm, self.settings.chat),
            agent=agent,
            queue=self.queue,
            settings=self.settings.chat,
        )
