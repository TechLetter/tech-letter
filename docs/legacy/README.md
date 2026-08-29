# 레거시 문서

2026-08-28 대격변 계획 수립 시 `docs/` 루트에서 이곳으로 이동한 구 설계 문서. **현행 코드와 일치하지 않는 부분이 많으며**(자세한 판정은 [plan/08 §8](../plan/09-current-state-audit.md)), 새 계획 문서(`docs/plan/`)가 이를 대체한다. Phase 10(정리)에서 삭제 예정.

| 문서 | 대체 |
|---|---|
| `auth.md` | plan/03 §0.2, §1.2 (OAuth/JWT 계약) |
| `admin.md` | plan/03 §2 |
| `internal-api-spec.md` | 폐기(내부 HTTP API가 사라짐) |
| `frontend_api_spec_phase2.md` | plan/03 |
| `chatbot_phase1.md`, `chatbot_phase2.md`, `chatbot_roadmap.md` | plan/01 §2~3, ADR-0004. Phase 3 로드맵(재랭킹/개인화)은 후속 과제로 별도 관리 |
| `msa_migration_plan.md` | plan/00, 05 (방향 자체가 MSA → 모놀리스로 바뀜) |
| `IDENTITY_POLICY_SYSTEM.md` | plan/04 §1.3 `identity_policies` |
| `DOCKER_MULTIPLATFORM.md` | 폐기(실배포는 ARM64 네이티브), plan/07 |

참고 가치가 있는 것: `auth.md`의 시퀀스 설명, `chatbot_phase2.md`의 크레딧 정책 서술(일 10개, 미사용 소멸, 402), `IDENTITY_POLICY_SYSTEM.md`의 identity_hash 설계 의도.
