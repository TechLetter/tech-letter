# 쉽게 읽기 (글별 해설)

글마다 원문을 한국 개발자용 한국어로 풀어 쓴 해설 페이지(`/posts/{id}`)다. 번역이 아니라 해설이다.
수집하는 블로그는 모두 저작권을 유보하고 있어서, 원문 문장을 옮기지 않고 새로 쓴다. 인용은 짧은
블록인용 2개까지만 허용한다. 출처(블로그·원문 링크)는 상세 화면에 늘 보인다.

## 1. 데이터
- `post_explainers` — 글마다 하나(`uniq_post_id`). 모델: `explainer/models.py`.
  - `tldr.one_liner`(카드에 보이는 한 문장), `tldr.points`(핵심 3줄), `body_md`(분량은 원문에 비례),
    `glossary`, `post_type`, `difficulty`, `reading_minutes`
  - `checks`(코드 검사 결과), `generation`(생성기·모델·프롬프트 버전·원문 해시)
- `posts.aisummary.summary`는 해설이 있는 글이면 TL;DR 한 문장이다. 예전 200자 요약은 2026-10-03에 폐기했다.
  `aisummary.points`(핵심 3줄)를 함께 둔다. 어휘(BM25) 색인과 챗봇 근거는 `AISummary.search_text()`(한 문장 + 3줄)를 읽는다.
- 글을 지우면 해설도 지운다(`PostRepository.delete`, `delete_by_blog`).

## 2. 생성
- 프롬프트: `explainer/prompt.py`(`PROMPT_VERSION`). 한 번의 호출로 JSON을 받는다.
- 분량: 목표 = 원문의 38%이고, 범위는 1,500~8,000자다. 짧은 글(공지 등)은 원문의 80%를 넘지 않게 한다.
- 코드 검사(`explainer/checks.py`) — 모델이 무엇이든 같은 기준을 적용한다.
  - 분량(목표의 0.7~1.8배)
  - 인용 비율 15% 이하, 원문을 30자 넘게 그대로 옮긴 비율 20% 이하
  - 숫자가 원문에 있는가. 단위 환산(30B → 300억)은 허용하고, 단위가 붙은 한 자리 숫자도 본다.
  - 코드 블록이 원문에 있는가
  - 한국어인가(원문에 없는 가나·키릴·한자가 섞이지 않았는가)
  - 섹션 수, TL;DR이 합니다체로 끝나는가
- 재시도: 검사에 걸리면 무엇이 모자랐는지(`feedback`) 덧붙여 다시 부른다. 그래도 걸리면 그 모델을 빼고
  다음 모델에게 맡긴다(최대 3회). 끝내 걸리면 검사 결과와 함께 저장한다.
- 모델의 JSON 실수에 대비한다.
  - `extract_json`은 첫 객체만 읽는다(`raw_decode`).
  - 문자열 안의 날것 줄바꿈도 받아들인다(`strict=False`).
  - Gemini는 JSON 모드(`response_mime_type`)로 부른다.

### 신규 글
2026-10-04에 200자 요약 기능을 폐기했다. 새 글은 원문을 받은 뒤(`content.fetch_requested`) 곧바로
해설을 만든다(`summary.requested` — 잡 이름은 예전 그대로). 모델 순서는 예전 요약과 같다:
3 Flash → 3.5 Flash Lite → OpenRouter 무료 모델.

참고로 2026-10-03 파일럿 40건을 Sonnet 블라인드로 채점한 결과는 다음과 같다.

| 생성기 | 사실성(0~2) | 중대 오류 |
|---|---|---|
| Codex gpt-6-luna | 1.97 | 0/39 |
| 3.5 Flash Lite 중심 체인 | 1.41 | 5/39 |

체인의 오류는 조건을 뒤집거나 수치를 바꾸는 의미 오류였고, 코드 검사로는 잡히지 않았다.
즉시성과 비용을 위해 이 체인을 쓰기로 했다.

## 3. 기존 글 백필 (2026-10-03)
- Codex 워커 100개(gpt-6-luna xhigh, 동시 55개)가 2,297건을 생성했다. 2,286건을 반영했고, 11건은
  원문이 기사가 아니라서(수집 오류 페이지) 거부됐다.
- 워커는 운영 프롬프트·검사를 그대로 쓰는 도구(저장소 밖 `plans/post-explainer/lib/kit.py`)로 쓰고 고친다.
- 반영 순서: DB 덤프 → 격리 컨테이너에서 같은 검사로 재검증·upsert → 카드 요약 교체 →
  `techletter backfill lexical --execute`로 어휘 색인 재생성.

## 4. API·화면
- `GET /posts/{id}/explainer` → `ExplainerOut`. 아직 없으면 404 `resource.not_found`.
  응답에 `X-Robots-Tag: noindex, nofollow`가 붙는다.
- 프론트 `/posts/:id`는 nginx가 `X-Robots-Tag: noindex, nofollow`를 붙인다(`try_files … =404`로 location 헤더 유지).
  - 사이트는 "기술 블로그 모음"으로만 검색되기를 원한다. 해설 본문은 색인되지 않게 한다.
- 화면에 "AI 해설" 같은 문구를 두지 않는다. 사이트 푸터의 고지 한 줄과 게시 중단 요청 메일만 둔다.
