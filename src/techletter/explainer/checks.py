"""쉽게 읽기 결과를 원문과 코드로 대조한다.

LLM 판정은 숫자 왜곡을 25% 정도만 잡는다는 보고가 있다(2026-10-03 조사 C). 그래서 먼저
코드로 거른다: 분량, 인용 비율, 원문을 그대로 옮긴 비율, 숫자가 원문에 있는지, 코드 블록이
원문에 있는지, 한국어로 썼는지, 섹션을 나눴는지, 합니다체인지. 어느 모델이 쓰든 같은
기준이다 — 걸리면 무엇이 모자란지 알려 주고 다시 쓰게 한다(`feedback`).
"""

from __future__ import annotations

import re

from techletter.explainer.models import ExplainerChecks

__all__ = ["MAX_QUOTE_RATIO", "check", "clean_body", "feedback", "min_sections"]

MAX_QUOTE_RATIO = 0.15
# 목표 분량에서 이만큼 벗어나도 허용한다. 모델이 글자 수를 정확히 맞추지 못한다.
LENGTH_TOLERANCE = (0.7, 1.8)
MIN_KOREAN_RATIO = 0.6
# 원문을 이만큼 이상 그대로 옮기면 해설이 아니라 발췌다. ">" 인용 없이 문단을 옮기는 모델이
# 있었다(2026-10-03 파일럿, 형식·대체성 점수 1.1).
MAX_COPY_RATIO = 0.2
COPY_SPAN = 30
# 원문에 없는 이런 문자가 이만큼 넘게 섞이면 언어가 샌 것이다(일본어·러시아어가 섞인 사례).
MAX_FOREIGN_CHARS = 3
CHARS_PER_SECTION = 700

# 두 자리 이상 숫자, 소수, 퍼센트·배수. 한 자리 숫자("3가지")는 흔해서 보지 않는다.
# 뒤에 붙은 단위로 크기를 환산해 같이 비교한다 — "30B"를 "300억"으로, "5k"를 "5,000"으로
# 옮기는 것은 정상이다.
_NUMBER = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{2,}|\d)\s?"
    r"(thousand|million|billion|trillion|[kKMB](?![A-Za-z])|천|만|억|조)?"
)
# 한 자리 숫자라도 이런 단위가 붙으면 본다 — "1,000RPM"을 "1RPM"으로 옮긴 사례(2026-10-03).
_UNIT_AFTER = re.compile(r"\s?(?:%|RPM|QPS|TPS|ms|[KMGT]B|배|x(?![A-Za-z]))")
_SCALE = {
    "k": 1e3,
    "K": 1e3,
    "thousand": 1e3,
    "천": 1e3,
    "M": 1e6,
    "million": 1e6,
    "만": 1e4,
    "B": 1e9,
    "billion": 1e9,
    "억": 1e8,
    "trillion": 1e12,
    "조": 1e12,
}
_CODE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_SPACE = re.compile(r"\s+")
_HEADING = re.compile(r"^## \S", re.M)
_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")
# 가나, 키릴, 한자. 한자는 원문에 있으면 허용한다("세태(世態)").
_FOREIGN = re.compile(r"[\u3040-\u30ff\u0400-\u04ff\u4e00-\u9fff]")
_EMPTY_QUOTE = re.compile(r"^>\s*$\n?", re.M)
_POLITE_END = re.compile(r"(니다|세요|까요)[.!?]?$")


def clean_body(body_md: str) -> str:
    """모델이 남기는 빈 인용 줄(">")을 지운다."""
    return _EMPTY_QUOTE.sub("", body_md).strip()


def min_sections(target_chars: int) -> int:
    """프롬프트는 700자당 섹션 하나를 바란다. 그 절반은 넘어야 한다."""
    return max(1, round(target_chars / CHARS_PER_SECTION / 2))


def _korean_ratio(text: str) -> float:
    prose = _CODE_BLOCK.sub(" ", text)
    hangul, latin = len(_HANGUL.findall(prose)), len(_LATIN.findall(prose))
    return hangul / (hangul + latin) if hangul + latin else 0.0


def _foreign_chars(prose: str, source: str) -> int:
    allowed = set(_FOREIGN.findall(source))
    return sum(1 for ch in _FOREIGN.findall(prose) if ch not in allowed)


def _copy_ratio(prose: str, source: str) -> float:
    """본문(공백 제거) 중 원문에 그대로 있는 30자 이상 구간이 덮는 비율."""
    body, src = _squash(prose), _squash(source)
    if len(body) < COPY_SPAN or len(src) < COPY_SPAN:
        return 0.0
    shingles = {src[i : i + COPY_SPAN] for i in range(len(src) - COPY_SPAN + 1)}
    covered = [False] * len(body)
    for i in range(len(body) - COPY_SPAN + 1):
        if body[i : i + COPY_SPAN] in shingles:
            covered[i : i + COPY_SPAN] = [True] * COPY_SPAN
    return round(sum(covered) / len(body), 3)


def _numbers(text: str) -> list[tuple[str, float | None, bool]]:
    """(쉼표 뺀 숫자, 단위로 환산한 크기, 측정 단위가 붙었나). 단위가 없으면 크기는 None."""
    found = []
    for m in _NUMBER.finditer(text):
        digits, unit = m.group(1), m.group(2)
        token = digits.replace(",", "")
        measured = bool(_UNIT_AFTER.match(text, m.end()))
        found.append((token, float(token) * _SCALE[unit] if unit else None, measured))
    return found


def _missing_numbers(prose: str, source: str) -> list[str]:
    tokens: set[str] = set()
    values: set[float] = set()
    for token, scaled, _ in _numbers(source):
        tokens.add(token)
        values.add(round(float(token), 6))
        if scaled is not None:
            values.add(round(scaled, 6))
    missing = set()
    for token, scaled, measured in _numbers(prose):
        if "." not in token and len(token) < 2 and not measured:
            continue  # 단위 없는 한 자리 정수("3가지")는 보지 않는다
        if token in tokens or round(float(token), 6) in values:
            continue
        if scaled is not None and round(scaled, 6) in values:
            continue
        missing.add(token)
    return sorted(missing)


def _squash(text: str) -> str:
    return _SPACE.sub("", text)


def check(
    body_md: str, source: str, target_chars: int, one_liner: str = "니다."
) -> ExplainerChecks:
    body_len = len(body_md)
    lo, hi = LENGTH_TOLERANCE
    quoted = sum(len(line) for line in body_md.splitlines() if line.lstrip().startswith(">"))
    ratio = round(quoted / body_len, 3) if body_len else 0.0

    # 코드 블록은 코드 대조가 따로 본다(원문 그대로여야 한다).
    prose = _CODE_BLOCK.sub(" ", body_md)
    missing = _missing_numbers(prose, source)
    copied = _copy_ratio(prose, source)

    squashed_source = _squash(source)
    code_ok = all(
        _squash(block) in squashed_source for block in _CODE_BLOCK.findall(body_md) if block.strip()
    )
    return ExplainerChecks(
        length_ok=lo * target_chars <= body_len <= hi * target_chars,
        quote_ratio=ratio,
        quote_ok=ratio <= MAX_QUOTE_RATIO,
        numbers_missing=missing[:20],
        code_ok=code_ok,
        copy_ratio=copied,
        copy_ok=copied <= MAX_COPY_RATIO,
        korean_ok=_korean_ratio(body_md) >= MIN_KOREAN_RATIO
        and _foreign_chars(prose, source) <= MAX_FOREIGN_CHARS,
        sections_ok=len(_HEADING.findall(body_md)) >= min_sections(target_chars),
        style_ok=bool(_POLITE_END.search(one_liner.strip())),
    )


def feedback(checks: ExplainerChecks, body_md: str, target_chars: int) -> str:
    """검사에 걸린 항목을 모델에게 그대로 알려 줄 문장들. 통과면 빈 문자열."""
    notes: list[str] = []
    if not checks.length_ok:
        lo, hi = LENGTH_TOLERANCE
        if len(body_md) < lo * target_chars:
            notes.append(
                f"body_md was {len(body_md)} characters; it must be at least "
                f"{int(target_chars * 0.85)}. Expand every section with the post's concrete "
                "details (how it works, why, numbers, trade-offs) and add sections for parts "
                "you skipped. Do not pad with repetition."
            )
        else:
            notes.append(
                f"body_md was {len(body_md)} characters; keep it under {int(hi * target_chars)}."
            )
    if not checks.sections_ok:
        notes.append(
            f'Split body_md into at least {min_sections(target_chars) + 1} "## " sections.'
        )
    if not checks.korean_ok:
        notes.append(
            "Write body_md in Korean only. Keep names and technical terms in English; "
            "no Japanese, Chinese or Cyrillic text."
        )
    if not checks.style_ok:
        notes.append('End tldr.one_liner in polite 합니다체 (for example "...했습니다.").')
    if not checks.copy_ok:
        notes.append(
            f"{round(checks.copy_ratio * 100)}% of body_md copies the post word for word. "
            "Explain in your own words instead of copying sentences."
        )
    if not checks.quote_ok:
        notes.append("Quote less: at most two short blockquotes.")
    if checks.numbers_missing:
        nums = ", ".join(checks.numbers_missing[:10])
        notes.append(f"These numbers are not in the post: {nums}. Use only numbers from the post.")
    if not checks.code_ok:
        notes.append("Code blocks must be copied exactly from the post, or removed.")
    return "\n".join(f"- {n}" for n in notes)
