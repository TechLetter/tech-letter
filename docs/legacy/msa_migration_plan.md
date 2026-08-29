# MSA 마이그레이션 실행 계획 및 진행 관리

- 기준일: `2026-02-16`
- 목표: 외부 공개 기능/계약 `100% 유지`를 전제로, API Gateway 비대화를 해소하고 MSA 베스트 프랙티스(명확한 서비스 책임, 신뢰성 있는 이벤트 처리, 무중단 전환)를 적용한다.
- 범위:
  - 포함: `api`, `content_service`, `user_service`, `chatbot_service`, `summary_worker`, `embedding_worker`, `retryworker`
  - 제외: UI 리디자인, 신규 비즈니스 기능 추가

---

## 1. 운영 원칙 (필수)

1. 외부 API 계약 고정
   - `/api/v1/*` 응답 스키마/상태코드는 기존과 동일 유지.
2. Strangler 방식 전환
   - 신규 경로를 병행 배치한 뒤 트래픽을 점진적으로 이동한다.
3. 이벤트 신뢰성 우선
   - 발행/적용 실패 시 데이터 정합성이 깨지지 않도록 outbox/inbox/멱등 처리를 우선한다.
4. 관측성 선행
   - 전환 전에 지표/로그/알람 기준을 먼저 확정한다.
5. 롤백 가능성 보장
   - 각 단계는 반드시 feature flag 또는 라우팅 스위치로 즉시 롤백 가능해야 한다.

---

## 2. 현재 스케줄러 + 이벤트 플로우 인벤토리

## 2.1 스케줄러

| 구분 | 현재 동작 | 근거 코드 |
| --- | --- | --- |
| RSS 수집 스케줄러 | `content_service` 프로세스 내부 스레드에서 30분 주기 실행 | `content_service/app/scheduler/rss_scheduler.py` |
| 스케줄러 시작/종료 | FastAPI lifespan에서 시작/종료 | `content_service/app/main.py` |

## 2.2 이벤트 파이프라인

| 플로우 | 현재 발행/소비 | 핵심 토픽 |
| --- | --- | --- |
| 포스트 요약 | content_service 발행 -> summary_worker 소비 -> content_service 반영 | `tech-letter.post.summary` |
| 포스트 임베딩 | content_service 발행 -> embedding_worker 소비 -> chatbot_service 반영 -> content_service 반영 | `tech-letter.post.embedding` |
| 채팅/크레딧 | user_service가 credit/chat 이벤트 발행, user_service chat consumer가 세션 반영 | `tech-letter.credit`, `tech-letter.chat` |
| 재시도/지연재주입 | retryworker가 `.retry.*` 토픽 재주입, 최대 초과 시 `.dlq` | 모든 기본 토픽 |

---

## 3. 목표 구조 (Scheduler + Event 관점)

1. 스케줄러 책임 분리
   - RSS 수집은 단일 실행 보장(leader election 또는 전용 scheduler 프로세스)으로 중복 수집 위험 제거.
2. 발행 신뢰성 강화
   - DB 변경과 이벤트 발행을 outbox로 결합.
3. 소비 멱등성 강화
   - 동일 이벤트 재수신 시 중복 반영 방지(inbox/event log).
4. 재처리 표준화
   - DLQ 운영 절차와 replay 도구를 표준화.
5. 버전 관리
   - 이벤트 schema 버전 필수 필드와 하위호환 정책을 문서화.

---

## 4. 워크스트림 A: API 단위 마이그레이션 계획

| ID | API | 현재 책임 | 목표 책임 | 전환 방식 | 롤백 |
| --- | --- | --- | --- | --- | --- |
| A-01 | `POST /api/v1/chatbot/chat` | gateway 오케스트레이션(세션검증/차감/환불) | conversation 서비스 | 신규 내부 API 도입 후 gateway 위임 | `CHAT_EXECUTOR=legacy` |
| A-02 | `GET /api/v1/users/profile` | gateway가 profile+credits 조합 | user_service | user 내부 조합 API 추가 후 gateway 프록시화 | `USER_PROFILE_MODE=legacy` |
| A-03 | `GET /api/v1/posts/bookmarks` | gateway가 bookmark+post 조합 | user_service 또는 content read-model | 내부 조합 API 신설 후 전환 | `BOOKMARK_POSTS_MODE=legacy` |
| A-04 | `GET /api/v1/posts*`, `/blogs`, `/filters*` | gateway 중계 + 일부 로직 | content_service | gateway read-only 변환만 유지 | 라우트별 legacy 스위치 |
| A-05 | `GET/POST/DELETE /api/v1/chatbot/sessions*` | gateway -> user 위임 | user_service | 계약 고정 + gateway thin화 | 기존 핸들러 유지 |
| A-06 | admin API (`/api/v1/admin/*`) | gateway role 체크 + 내부 호출 | domain 서비스 자체 검증 추가 | 서비스 레벨 권한 검증 병행 도입 | `ADMIN_AUTH_MODE=gateway_only` |

---

## 5. 워크스트림 B: Scheduler + Event 기능 계획

| ID | 영역 | 작업 내용 | 완료 기준 | 위험 | 롤백/완화 |
| --- | --- | --- | --- | --- | --- |
| B-01 | RSS Scheduler | 단일 실행 보장 전략 적용(리더락 또는 전용 scheduler 프로세스) | 동일 시간대 중복 수집 0건 | 다중 인스턴스 중복 실행 | 기존 `content_service` 내 스레드 모드로 즉시 복귀 |
| B-02 | RSS -> Summary 이벤트 | 신규 포스트 insert + `post.summary_requested` 발행을 outbox로 전환 | insert 성공 시 이벤트 유실 0 | outbox 전환 중 지연 증가 | dual-write 기간 운영 후 cutover |
| B-03 | Summary Worker | `post.summary_requested` 소비 멱등화(`event_id` 처리 기록) | 동일 이벤트 재처리 시 결과 동일 | 중복 요약 비용 증가 | 기존 로직 유지 + inbox 테이블/컬렉션 비활성화 |
| B-04 | Summary 적용 | content_service `post.summary_response` 반영 멱등화 | 동일 event 재수신 시 문서 상태 불변 | 상태 덮어쓰기 레이스 | 버전/updated_at 조건부 업데이트 |
| B-05 | Embedding Worker | 캐시 + 이벤트 멱등성 강화, chunk 결과 결정성 검증 | 같은 입력에서 chunk 수/벡터 차원 일관 | 모델 변경 시 호환성 이슈 | 모델 버전 분리 컬렉션 유지 |
| B-06 | Embed 적용 | chatbot upsert 후 `post.embedding_applied` 발행 보장(outbox) | upsert 성공 후 applied 이벤트 누락 0 | upsert/발행 분리로 정합성 깨짐 | 재발행 리컨실러 배치 |
| B-07 | Embedding 상태 반영 | content_service의 applied 이벤트 반영 멱등화 | 중복 이벤트에도 `status.embedded=true` 유지 | 중복 update 부하 | inbox 캐시 + idempotent update |
| B-08 | Chat 이벤트 소비 | user_service chat consumer stop 제어/타입필터/오류 처리 표준화 | 비정상 종료 시 메시지 유실 없음 | 현재 스레드 stop 제어 부재 | 기존 consumer 코드 유지 가능하도록 feature flag |
| B-09 | Retry/DLQ 운영 | `.retry.*`, `.dlq` 모니터링 및 replay runbook 문서화 | DLQ 수동재처리 절차 검증 완료 | 장기 적체 | 배치 replay 툴/알람 임계치 적용 |
| B-10 | 스키마 버전 관리 | 이벤트 필수 필드/버전 호환 정책 확정 | 신규 버전 배포 시 소비자 장애 0 | 파서 호환성 깨짐 | producer canary + consumer tolerant reader |

---

## 6. 단계별 실행 계획 (권장 순서)

### Phase 0. 기준선/가드레일 (1주)

1. 공개 API 계약 스냅샷 테스트 고정(`swagger` 기준).
2. 라우트별 feature flag 설계(`legacy/new`).
3. 핵심 지표 정의:
   - API: p95 latency, 4xx/5xx rate
   - 이벤트: lag, retry, dlq 건수, end-to-end 처리 시간
4. 전환 승인 게이트 문서화.

### Phase 1. Chat 오케스트레이션 분리 (2주)

1. `A-01` 구현 및 카나리(5% -> 25% -> 100%).
2. `B-08`, `B-09` 동시 적용.
3. 성공 기준: 크레딧 차감/환불 정합성 100%.

### Phase 2. User/Profile/Bookmark 조합 이관 (1~2주)

1. `A-02`, `A-03` 구현.
2. 프로필 조회/북마크 목록 응답 스키마 완전 일치 검증.

### Phase 3. Scheduler/Event 신뢰성 강화 (2주)

1. `B-01`~`B-07`, `B-10` 구현.
2. outbox/inbox 적용 및 replay 검증.

### Phase 4. Admin/Auth 경계 강화 + 정리 (1주)

1. `A-06` 적용.
2. gateway 내 불필요 오케스트레이션 코드 제거.

---

## 7. 진행 관리 보드 (PR 단위 업데이트용)

상태 규칙:

- `TODO`: 시작 전
- `DOING`: 진행 중
- `DONE`: 운영 반영 완료
- `BLOCKED`: 외부 의존/이슈로 중단

| ID | 워크스트림 | 작업 | 상태 | 담당 서비스 | 목표 PR | 완료일 | 메모 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | API | chatbot chat 오케스트레이션 분리 | TODO | api + conversation | - | - | - |
| A-02 | API | users/profile 조합 이관 | TODO | api + user_service | - | - | - |
| A-03 | API | posts/bookmarks 조합 이관 | TODO | api + user_service/content_service | - | - | - |
| A-04 | API | content read API thin gateway화 | TODO | api + content_service | - | - | - |
| A-05 | API | chatbot sessions 경로 thin gateway화 | TODO | api + user_service | - | - | - |
| A-06 | API | admin 권한 검증 서비스 레벨 추가 | TODO | api + user_service + content_service | - | - | - |
| B-01 | Event | RSS 단일 실행 보장 | TODO | content_service | - | - | - |
| B-02 | Event | summary 요청 outbox 전환 | TODO | content_service | - | - | - |
| B-03 | Event | summary worker 멱등 소비 | TODO | summary_worker | - | - | - |
| B-04 | Event | summary 적용 멱등 처리 | TODO | content_service | - | - | - |
| B-05 | Event | embedding worker 멱등/결정성 | TODO | embedding_worker | - | - | - |
| B-06 | Event | embed 적용 후 applied 발행 보장 | TODO | chatbot_service | - | - | - |
| B-07 | Event | embedding 상태 반영 멱등 처리 | TODO | content_service | - | - | - |
| B-08 | Event | chat consumer 안정화(정지/필터) | TODO | user_service | - | - | - |
| B-09 | Event | retry/dlq runbook + replay | TODO | retryworker | - | - | - |
| B-10 | Event | 이벤트 버전 호환 정책 확정 | TODO | common + 전 서비스 | - | - | - |

---

## 8. 검증 체크리스트 (각 단계 공통)

1. 계약 테스트
   - `/api/v1/*` 상태코드/응답 키 일치.
2. 기능 테스트
   - 로그인, 포스트 조회, 북마크, 챗봇, 어드민 지급 회귀.
3. 이벤트 테스트
   - 재시도/중복 수신 상황에서 최종 상태 정합성 확인.
4. 운영 테스트
   - canary 구간에서 error rate 임계치(예: +0.5%p 이상 증가 금지) 만족.
5. 롤백 테스트
   - feature flag 전환 후 10분 내 정상 회복.

---

## 9. 변경 이력

| 날짜 | 변경 내용 | 작성자 |
| --- | --- | --- |
| 2026-02-16 | 초기 마이그레이션 계획/진행 보드 생성 | codex |

