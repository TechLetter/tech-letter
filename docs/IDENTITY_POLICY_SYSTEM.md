# Identity Policy System (식별자 기반 정책 엔진)

## 1. 개요 (Overview)

**Identity Policy System**은 유저 계정(User Profile)의 생명주기와 독립적으로, **고유 식별자(Identity)** 단위의 비즈니스 규칙을 적용하기 위한 시스템입니다.

기존의 `User` 테이블에 의존하는 로직은 유저가 "탈퇴 후 재가입"을 반복할 경우 이력을 추적할 수 없는 한계가 있습니다. 이 시스템은 **SHA-256 해시화된 식별자**를 영구적으로 보관하여, 계정 상태와 무관하게 강력한 정책(어뷰징 방지, 1회 한정 혜택 등)을 집행합니다.

---

## 2. 아키텍처 (Architecture)

### 2.1 데이터 모델

모든 데이터는 `identity_policies` MongoDB 컬렉션에 저장됩니다.

| 필드            | 타입            | 설명                                                      |
| --------------- | --------------- | --------------------------------------------------------- |
| `identity_hash` | `String`        | 유저 식별자의 해시값 (PK). `SHA256(provider + ":" + sub)` |
| `policy_key`    | `String (Enum)` | 적용된 정책의 종류 (예: `DAILY_CREDIT_GRANT`)             |
| `last_acted_at` | `DateTime`      | 정책이 마지막으로 적용(성공)된 시각 (UTC)                 |
| `created_at`    | `DateTime`      | 최초 생성 시각                                            |

> **Unique Index**: `(identity_hash, policy_key)` 복합 유니크 인덱스가 걸려 있어, 동일 정책의 중복 생성을 DB 레벨에서 차단합니다.

### 2.2 핵심 로직 (Atomic Check-and-Set)

동시성 이슈(Race Condition)를 방지하기 위해 애플리케이션 레벨의 조회가 아닌, **데이터베이스의 원자적 연산(Atomic Operation)**을 사용합니다.

1. **Hash 생성**: 유저의 `provider`와 `sub`를 조합하여 해시를 생성합니다. (개인정보 보호를 위해 원본 저장 안 함)
2. **Atomic Update**:
   - 조건: `identity_hash`와 `policy_key`가 일치하고, `last_acted_at`이 기준 시간(Window)보다 과거인 경우.
   - 행동: `last_acted_at`을 현재 시간으로 갱신.
3. **결과 판정**:
   - `modified_count == 1`: 업데이트 성공 → 정책 적용 가능 (True)
   - `modified_count == 0`: 조건 불만족 (이미 최근에 적용됨) → 정책 적용 불가 (False)

---

## 3. 확장 가이드 (Extensibility)

새로운 비즈니스 정책을 추가하려면 다음 단계만 거치면 됩니다.

### 3.1 PolicyKey Enum 추가

`common/common/models/identity_policy.py` 파일의 `PolicyKey` Enum에 새 키를 추가합니다.

```python
class PolicyKey(StrEnum):
    DAILY_CREDIT_GRANT = "DAILY_CREDIT_GRANT"
    WELCOME_BONUS = "WELCOME_BONUS"  # [NEW] 신규 가입 혜택
    EVENT_2026_PROMO = "EVENT_2026_PROMO"  # [NEW] 이벤트 참여
```

### 3.2 서비스 로직 적용

`IdentityPolicyRepository.try_use_policy` 메서드를 호출하여 정책을 검증합니다.

```python
# 예시: 웰컴 보너스 지급 (재가입해도 평생 1회만 가능)
is_eligible = policy_repo.try_use_policy(
    identity_hash=hash,
    policy_key=PolicyKey.WELCOME_BONUS,
    window_hours=999999 # 사실상 무제한 (평생 1회)
)

if is_eligible:
    grant_welcome_bonus(user)
```

---

## 4. 자주 묻는 질문 (FAQ)

**Q. 유저가 탈퇴하면 이 데이터도 삭제되나요?**
A. 아니요. 어뷰징 방지 및 정책 유지를 위해 `identity_policies` 데이터는 유저 탈퇴 후에도 보존됩니다. 단, 개인을 식별할 수 없는 해시값 형태이므로 개인정보보호법 및 Privacy Policy를 준수합니다.

**Q. 일일 지급 기준 시간은 언제인가요?**
A. 시스템 내부적으로 **UTC**를 기준 시간으로 사용합니다. `window_hours=24`는 정확히 24시간이 지난 시점을 의미하는 것이 아니라, 로직에 따라 "마지막 지급일이 오늘이 아닌 경우" 등으로 응용될 수 있습니다. 현재 로직은 `last_acted_at` 갱신 방식이므로 순수 시간 차이를 기준으로 합니다.

**Q. Redis가 아닌 MongoDB를 사용하는 이유는?**
A. 데이터의 영속성(Persistence)이 중요하기 때문입니다. Redis는 인메모리 특성상 데이터 유실 가능성이 있고, 장기간(수년) 보관해야 하는 정책 데이터(예: 웰컴 보너스 이력)에는 DB가 더 적합합니다.
