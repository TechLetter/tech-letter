from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .exceptions import SummarizationError


# Go cmd/processor/summarizer.SYSTEM_INSTRUCTION과 동일한 역할을 하는 시스템 프롬프트.
SYSTEM_INSTRUCTION = """\
You are a content summarization assistant for technical blog posts.
Your task is to analyze the provided text and produce a structured summary.
The response MUST be a valid JSON object with five keys:

1. summary:
    Write a concise summary of the blog post in Korean from a technical perspective. 
    Use only technical terms that appear in the original post and do not add any new information. 
    Select only 1–2 main technical points and do not expand further with step-by-step implementation details or extra optimizations. 
    Make it polite and approximately 150–180 tokens. 
    After generation, trim the output to approximately 200 characters (±10 characters) if it exceeds this range. 
    End the summary by briefly suggesting what the reader can observe or learn from this post, without asserting it as a guaranteed benefit.
2. categories: A list of 1–3 categories that best describe the blog post.
   You MUST choose only from the following predefined category list (English terms):
   ["Backend", "Frontend", "Mobile", "AI", "Data Engineering", "DevOps", "Security",
    "Cloud", "Database", "Programming Languages", "Infrastructure", "Other"].
3. tags: A list of 3–7 keywords that represent the **specific technologies, libraries, frameworks,
   tools, languages, or protocols** explicitly mentioned in the text.
   - Tags MUST be concrete and reusable English terms (e.g., "Hadoop", "React", "Kubernetes").
   - Do NOT include generic concepts (e.g., "AI development", "storage cost") or long phrases.
   - Remove duplicates.
4. error: An optional string field. If the input text contains bot-verification messages \
or HTTP error indicators such as "I'm not a robot", "verify you are human", "bot check", "404 not found", "403 forbidden", "500 internal server error", "bad request", "gateway timeout", \
or any similar access-error content, or if the blog content cannot be determined due to missing, empty, or invalid text, \
set this field to a short descriptive Korean error message. Otherwise, set it to null.


Additional constraints:
- Only 'summary' should be written in Korean. All other fields (categories, tags) remain in English.
- You MUST NOT wrap the JSON output in a markdown code block (e.g., ```json ... ```).
- The response should contain ONLY the raw JSON string.
- If summarization fails, set the 'error' field to an appropriate message (e.g., "Content contains a security check preventing summarization.")
  and provide an empty string for 'summary', and empty arrays for 'categories' and 'tags'.
"""


class SummarizeResult(BaseModel):
    summary: str = Field(default="")
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    error: str | None = None


# ── 모듈 레벨에서 한 번만 생성 (불변 객체) ──────────────────────────
_parser = PydanticOutputParser(pydantic_object=SummarizeResult)
_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_INSTRUCTION + "\n\n{format_instructions}"),
        ("human", "{text}"),
    ]
).partial(format_instructions=_parser.get_format_instructions())


def _call_llm(chat_model: BaseChatModel, text: str) -> SummarizeResult:
    """Go SummarizeText(text string)와 동일하게 동작하도록 LLM을 호출한다."""
    chain = _prompt | chat_model | _parser
    return chain.invoke({"text": text})


def summarize_post(*, chat_model: BaseChatModel, plain_text: str) -> SummarizeResult:
    result = _call_llm(chat_model, plain_text)

    if result.error:
        # Go 구현과 마찬가지로 error 필드가 설정된 경우에는 실패로 간주하고 예외를 던진다.
        raise SummarizationError(
            f"ai judged that this content is not summarizable: {result.error}",
        )
    return result
