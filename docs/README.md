# Tech-Letter 문서

프로젝트 개요는 루트 [README.md](../README.md) 참조. 여기는 아키텍처·운영 상세 문서다.

## 아키텍처 (`architecture/`)
| 문서 | 내용 |
|---|---|
| [architecture](architecture/architecture.md) | 프로세스 4종, 모듈러 모놀리스 레이아웃, 잡 큐, LLM 라우터, 관측, 보안 |
| [directory-structure](architecture/directory-structure.md) | `src/techletter` 트리, `pyproject.toml`, 설정 트리, 코드 규약 |
| [api-contract](architecture/api-contract.md) | API 계약: 봉투·에러 코드·리소스 스키마·엔드포인트·SSE |
| [data-model](architecture/data-model.md) | MongoDB 컬렉션·인덱스, Qdrant, 환경변수 이름 |
| [testing-strategy](architecture/testing-strategy.md) | 단위·계약·통합·E2E, CI 구성, 배포 스모크 |
| [deployment-and-ops](architecture/deployment-and-ops.md) | 배포 파이프라인, compose 구성, 관측 기준선, 런북, 롤백 |

## 기타
- [PRIVACY_POLICY.md](PRIVACY_POLICY.md) — 개인정보처리방침
- `images/` — README 이미지
- 배포 절차(커밋부터 검증까지)는 워크스페이스 루트 `AGENTS.md`("변경사항 배포")
