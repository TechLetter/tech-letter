# Tech-Letter 문서

> **2026-08-28 — 백엔드 대격변(Great Rewrite) 계획 단계.** 결정 인터뷰가 끝나 문서를 개정했고, **코드는 아직 변경되지 않았다**. 현재 운영 중인 구조의 설명은 루트 [README.md](../README.md) 참조.
>
> **지금 필요한 것: [04-api-v2.md](plan/04-api-v2.md) 리뷰** — 새 API 계약에 합의하면 Phase 0부터 착수한다.

## 읽는 순서
1. [00-overview](plan/00-overview.md) — 왜/무엇을/제약, **결정 로그 21건**, 성공 기준, 리스크
2. [**04-api-v2**](plan/04-api-v2.md) — ⭐ **새 API 계약 제안(리뷰 핵심)**: 경로·스키마·에러 체계·프론트 변경 체크리스트
3. [06-migration-steps](plan/06-migration-steps.md) — Phase 0~11, 85스텝, 진행 보드

## 계획 (`plan/`)
| 문서 | 내용 |
|---|---|
| [00-overview](plan/00-overview.md) | 목표·비목표·**결정 로그**·제약·토폴로지·DoD·리스크 |
| [01-target-architecture](plan/01-target-architecture.md) | 프로세스 4종, 모듈러 모놀리스, **Mongo 잡 큐**, LLM 라우터, 관측 |
| [02-directory-structure](plan/02-directory-structure.md) | `src/techletter` 트리, `pyproject.toml`, 설정 트리, 코드 규약 |
| [03-api-current](plan/03-api-current.md) | **현행** 계약 기록(프론트가 실제로 읽던 필드) — 이식 참조·스냅샷 기준 |
| [04-api-v2](plan/04-api-v2.md) | ⭐ **새 계약**: 봉투 통일, 에러 코드 체계, 경로 정리, 어드민 운영 API |
| [05-data-contract](plan/05-data-contract.md) | MongoDB 컬렉션·인덱스(유지/신설), Qdrant, **Kafka 삭제 절차**, 시크릿 이름 |
| [06-migration-steps](plan/06-migration-steps.md) | Phase 0~11 실행 스텝(**프론트 Phase 8** 포함) |
| [07-testing-strategy](plan/07-testing-strategy.md) | 단위·계약·통합·**Playwright E2E**, 컷오버 스모크 |
| [08-deployment-and-ops](plan/08-deployment-and-ops.md) | 운영 현황, 새 파이프라인, compose, 관측 기준선, 런북, 롤백, IaC 정리 |
| [09-current-state-audit](plan/09-current-state-audit.md) | 코드·운영 전수 감사 압축본(실측 데이터) |

## 결정 기록 (`plan/adr/`)
| ADR | 결정 |
|---|---|
| [0001](plan/adr/0001-modular-monolith.md) | FastAPI 모듈러 모놀리스 + 워커 프로세스 분리 |
| [0002](plan/adr/0002-drop-go.md) | Go 전면 제거, Python 단일 언어 |
| [0003](plan/adr/0003-async-stack.md) | asyncio 단일 스택(PyMongo Async, AsyncQdrantClient, httpx, async_playwright) |
| [0004](plan/adr/0004-mongo-job-queue.md) | **Kafka 전면 제거 → MongoDB `jobs` 단일 잡 큐** |
| [0005](plan/adr/0005-project-layout.md) | `src/techletter` 단일 패키지, 도메인 패키지 |
| [0006](plan/adr/0006-tooling.md) | Python 3.12, uv, ruff, pyright, pytest, pre-commit, CI |
| [0007](plan/adr/0007-api-contract-redesign.md) | **API 계약 전면 재설계 + 프론트 동시 수정** |
| [0008](plan/adr/0008-llm-model-router.md) | **LLM 모델 라우터**(큐레이션 ∩ scouter 헬스, Gemini 우선 이중화) |

## 이슈 (`issues/`)
[issues/README.md](issues/README.md) — 25건. 결정으로 해소된 6건(요약 쿼터·임베딩 캐시·Kafka 3종·챗봇 장애·프론트)과 범위 제외 1건([ISSUE-018](issues/ISSUE-018-iac-hardcoded-secrets.md) Mongo 비밀번호)을 표시.

## 기타
- [PRIVACY_POLICY.md](PRIVACY_POLICY.md) — 개인정보처리방침(현행 유지)
- [legacy/](legacy/README.md) — 구 설계 문서(Phase 11에서 삭제)
- `swagger.json` / `swagger.yaml` / `docs.go` — Go swag 산출물(Go 빌드가 참조하므로 Phase 11까지 유지)
- `images/` — README 이미지
- 배포 절차: 워크스페이스 루트 `AGENTS.md`("변경사항 배포")
