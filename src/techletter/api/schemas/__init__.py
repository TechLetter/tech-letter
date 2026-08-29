"""API DTO — 04 문서와 1:1로 대응한다.

도메인 모델을 그대로 내보내지 않는 이유: DB 필드명(`aisummary`,
`status.ai_summarized`)이 계약과 다르고, 내부 식별자(`provider_sub`,
`user_code`, 잡 `payload`)를 노출하면 안 되기 때문이다.
"""

from techletter.api.schemas.admin import (
    BackfillIn,
    BackfillStatusOut,
    BlogIn,
    JobOut,
    JobStatsOut,
    LlmModelStatOut,
    PostIn,
    RetryBulkIn,
)
from techletter.api.schemas.chat import (
    ChatAnswerOut,
    ChatMessageOut,
    ChatSessionOut,
    MessageIn,
    SuggestedQuestionIn,
    SuggestedQuestionOut,
)
from techletter.api.schemas.common import ErrorBody, JobAccepted, Listing, Paged
from techletter.api.schemas.content import (
    AdminBlogOut,
    AdminPostOut,
    BlogFilterOut,
    BlogOut,
    FilterOut,
    PostOut,
    RisingTagsOut,
    SourceOut,
    TrendSeriesOut,
)
from techletter.api.schemas.user import (
    AdminUserOut,
    BookmarkIn,
    BookmarkOut,
    CreditGrantIn,
    CreditGrantOut,
    MeOut,
    TokenIn,
    TokenOut,
)

__all__ = [
    "AdminBlogOut",
    "AdminPostOut",
    "AdminUserOut",
    "BackfillIn",
    "BackfillStatusOut",
    "BlogFilterOut",
    "BlogIn",
    "BlogOut",
    "BookmarkIn",
    "BookmarkOut",
    "ChatAnswerOut",
    "ChatMessageOut",
    "ChatSessionOut",
    "CreditGrantIn",
    "CreditGrantOut",
    "ErrorBody",
    "FilterOut",
    "JobAccepted",
    "JobOut",
    "JobStatsOut",
    "Listing",
    "LlmModelStatOut",
    "MeOut",
    "MessageIn",
    "Paged",
    "PostIn",
    "PostOut",
    "RetryBulkIn",
    "RisingTagsOut",
    "SourceOut",
    "SuggestedQuestionIn",
    "SuggestedQuestionOut",
    "TokenIn",
    "TokenOut",
    "TrendSeriesOut",
]
