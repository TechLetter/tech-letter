import pytest
from summary_worker.app.validator import validate_plain_text
from summary_worker.app.exceptions import ValidationError


def test_validate_plain_text_valid():
    """정상적인 텍스트는 통과해야 한다."""
    # 200자 이상이어야 안전함
    text = "This is a valid technical blog post about Python and AI. " * 20
    assert len(text) > 200
    validate_plain_text(text)


def test_validate_plain_text_empty():
    """빈 텍스트는 에러를 발생시켜야 한다."""
    with pytest.raises(ValidationError, match="content_empty"):
        validate_plain_text("")

    with pytest.raises(ValidationError, match="content_empty"):
        validate_plain_text("   ")


def test_validate_plain_text_too_short():
    """너무 짧은 텍스트(50자 미만)는 에러를 발생시켜야 한다."""
    text = "Too short"
    with pytest.raises(ValidationError, match="content_too_short"):
        validate_plain_text(text)


def test_validate_plain_text_strong_block():
    """Strong block 키워드 에러."""
    keywords = [
        "verify you are human",
        "bot check",
        "access denied",
        "security check",
        "cloudflare",
    ]
    for kw in keywords:
        text = f"Please {kw} to continue...".ljust(60, ".")

        with pytest.raises(ValidationError, match=f"strong_block:{kw}"):
            validate_plain_text(text)


def test_validate_plain_text_strong_block_always_for_cloudflare_like_pages():

    text = (
        "medium.com\nVerifying you are human. This may take a few seconds. "
        "medium.com needs to review the security of your connection before proceeding. "
        "Please unblock challenges.cloudflare.com to proceed. Verification successful "
        "Waiting for medium.com to respond..."
    )

    assert len(text) < 1000
    with pytest.raises(
        ValidationError,
        match="strong_block:verify you are human|strong_block:cloudflare|strong_block:challenges.cloudflare.com",
    ):
        validate_plain_text(text)


def test_validate_plain_text_unknown_content():
    """Unknown content 패턴이 포함되고 길이가 1000자 미만인 경우 에러."""
    keywords = ["just a moment", "redirecting", "loading...", "checking your browser"]
    for kw in keywords:
        # 50자 이상 100자 미만으로 맞춤
        text = f"Please wait, {kw}".ljust(60, ".")
        assert len(text) < 1000

        with pytest.raises(ValidationError, match=f"unknown_content:{kw}"):
            validate_plain_text(text)


def test_validate_plain_text_soft_block():
    """Soft block 키워드가 포함되고 길이가 500자 미만인 경우 에러."""
    keywords = [
        "not found",
        "forbidden",
        "internal server error",
        "bad request",
        "gateway timeout",
    ]
    for kw in keywords:
        # 50자 이상 500자 미만으로 맞춤
        text = f"Error occurred: {kw}".ljust(60, ".")
        assert len(text) < 500

        with pytest.raises(ValidationError, match=f"soft_block:{kw}"):
            validate_plain_text(text)


def test_validate_plain_text_soft_block_ignored_if_long():
    """Soft block 키워드가 있어도 텍스트가 500자 이상이면 통과해야 한다."""
    # 200자 이상의 텍스트 생성
    long_text = "This is a long blog post about handling HTTP errors. " * 10
    long_text += (
        "Sometimes you might encounter a 404 not found error when developing APIs. "
    )
    long_text += "Here is how to handle it properly in your code. " * 10

    assert len(long_text) >= 500
    # 에러가 발생하지 않아야 함
    validate_plain_text(long_text)
