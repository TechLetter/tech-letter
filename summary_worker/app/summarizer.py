from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


# Go cmd/processor/summarizer.SYSTEM_INSTRUCTION과 동일한 역할을 하는 시스템 프롬프트.
SYSTEM_INSTRUCTION = """
You are a content summarization assistant for technical blog posts.
Your task is to analyze the provided text and produce a structured summary.
The response MUST be a valid JSON object with five keys:

1. summary: A concise summary of the blog post, no more than 200 characters. Always be polite.
   (Written in Korean)
2. error: An optional string field. If the content contains a security check
   (e.g., "I'm not a bot," "Are you human?") that prevents summarization,
   set this field to a descriptive error message. Otherwise, set it to 'null'.
4. categories: A list of 1–3 categories that best describe the blog post.
   You MUST choose only from the following predefined category list (English terms):
   ["Backend", "Frontend", "Mobile", "AI", "Data Engineering", "DevOps", "Security",
    "Cloud", "Database", "Programming Languages", "Infrastructure", "Other"].
5. tags: A list of 3–7 keywords that represent the **specific technologies, libraries, frameworks,
   tools, languages, or protocols** explicitly mentioned in the text.
   - Tags MUST be concrete and reusable terms (e.g., "Hadoop", "React", "Kubernetes").
   - Do NOT include generic concepts (e.g., "AI development", "storage cost") or long phrases.
   - Remove duplicates.

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


def _call_llm(chat_model: BaseChatModel, text: str) -> SummarizeResult:
    """Go SummarizeText(text string)와 동일하게 동작하도록 LLM을 호출한다."""
    parser = PydanticOutputParser(pydantic_object=SummarizeResult)

    # format_instructions 안에 JSON 예시 등 중괄호가 포함되므로,
    # 이를 직접 문자열 결합해 템플릿에 넣으면 ChatPromptTemplate이
    # 잘못된 변수({"foo"}, {"properties"} 등)로 해석한다.
    # 따라서 별도 변수로 두고 partial()로 고정 주입한다.

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_INSTRUCTION + "\n\n{format_instructions}"),
            ("human", "{text}"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | chat_model | parser
    return chain.invoke({"text": text})


def summarize_post(*, chat_model: BaseChatModel, plain_text: str) -> SummarizeResult:
    result = _call_llm(chat_model, plain_text)

    if result.error:
        # Go 구현과 마찬가지로 error 필드가 설정된 경우에는 실패로 간주하고 예외를 던진다.
        raise RuntimeError(
            f"ai judged that this content is not summarizable: {result.error}",
        )
    return result
