# Aggregate & Processor 단순화 설계 (Tidy First 관점)

## 1. 목표

RAG 기반 챗봇 도입 전에, Tech-Letter의 **Aggregate ↔ Processor 파이프라인**을 더 단순하고 명확하게 만든다.

현재 구조는 이벤트 드리븐을 강조하기 위해 Processor 내부 단계까지 이벤트로 쪼개져 있어, 다음과 같은 문제가 있다.

- 이벤트 타입이 많고, 실제로는 **같은 프로세스 내부 단계**까지 이벤트로 나뉘어 있음
- 한 포스트 처리 파이프라인의 전체 그림을 한 눈에 파악하기 어렵다
- RAG 인덱서를 어디에 붙여야 할지(어떤 이벤트를 기준으로 할지) 직관적이지 않다

이 문서는 다음을 목표로 한다.

1. Aggregate가 수행해야 하는 역할을 **간결하게 재정의**
2. Processor가 `PostCreated` 이벤트만 받아 **내부 단계(HTML 렌더링/파싱/요약)를 통합**하는 파이프라인으로 단순화
3. 외부에서 의미 있는 이벤트 경계(예: `PostCreated`, `PostSummarized`)만 깔끔하게 남기기

---

## 2. 원하는 최종 플로우 (요약)

텍스트로 표현하면 다음과 같다.

1. **Aggregate**

   - 설정된 블로그 리스트(config.yaml 기반)의 각 RSS 피드를 조회
   - MongoDB에 기존 데이터와 비교하여 **새로 추가된 항목만** 저장
   - 새로 추가된 포스트에 대해서만 `PostCreated` 이벤트 발행

2. **Processor**

   - `PostCreated` 이벤트만 구독
   - 해당 포스트에 대해 **HTML 렌더링 → 텍스트 파싱 → AI 요약**을 하나의 파이프라인으로 처리
   - 중간 단계들(HTML 렌더링 완료, 텍스트 파싱 완료)은 **Processor 내부 로직**으로 통합하고, 외부 이벤트로 쪼개지 않음
   - 처리 완료 후 **MongoDB에는 직접 접근하지 않고**, 요약 결과를 담은 `PostSummarized` 이벤트만 발행
   - `PostThumbnailRequested` 이벤트를 구독
   - HTML 렌더링 및 썸네일 파싱(메타 태그, `<link>`, `<img>` + 실제 이미지 사이즈 검사)을 수행
   - 결과를 `PostThumbnailParsed` 이벤트로 발행

3. **Aggregate**

   - `PostThumbnailParsed` 이벤트를 구독하여 `thumbnail_url` 필드와 `status.thumbnail_parsed` 플래그를 업데이트

4. **(미래) RAG 인덱서**

   - `PostSummarized` 이벤트만 구독하여 벡터 인덱싱 수행

---

## 3. Aggregate 역할 재정의

### 3.1 현재 Aggregate 개략 구조

- `cmd/aggregate/main.go`

  - `config.InitApp()`, `config.InitLogger()`
  - `db.Init(ctx)`
  - `eventbus.GetBrokers()`, `EnsureTopics`, `NewKafkaEventBus`
  - `EventService`와 `AggregateService` 초기화
  - 주기적으로 `AggregateService.RunFeedCollection(ctx)` 실행

- `AggregateService` (개략)
  - RSS 피드 수집 (feeder 사용)
  - MongoDB에 포스트 저장
  - 새 포스트에 대해 요약 요청 이벤트(`EventService.PublishPostCreated`, type=`PostCreated`) 호출

### 3.2 목표 역할

Aggregate는 다음 두 가지에만 집중하도록 단순화한다.

1. **RSS 수집**

   - `config.yaml` 에 정의된 blog 리스트(이름, RSS URL 등)를 순회
   - 각 블로그에 대해 RSS 피드를 가져온다.

2. **신규 포스트 감지 & 이벤트 발행**
   - RSS 항목별로 MongoDB를 조회하여 "이미 존재하는 포스트인지"를 판별
     - 기준: 보통 `link` 또는 RSS `guid`
   - 존재하지 않는 항목에 대해서만:
     - MongoDB에 새 `Post` 도큐먼트를 삽입
     - 요약 요청 이벤트인 `PostCreated` 발행

> Aggregate는 **요약, HTML 렌더링, 텍스트 파싱 등 콘텐츠 처리에는 관여하지 않고**, 단지 "새 글이 생겼다"는 사실만 Processor에게 알려주는 역할에 집중한다.

---

## 4. Processor 역할 재정의

### 4.1 현재 Processor 흐름 (요약)

- `cmd/processor/main.go`

  - EventBus 구독: `TopicPostEvents`
  - Kafka 메시지를 디코딩 후 `events.BaseEvent.Type` 에 따라 switch
  - `PostCreated` 타입에 대해서만 `EventHandlers.HandlePostCreated`를 호출

- `EventHandlers` (`cmd/processor/handlers/event_handlers.go`)

  - `HandlePostCreated` 내부에서:
    - `PostCreated` 이벤트의 `Link`를 사용해 HTML 렌더링 → 텍스트 파싱 → AI 요약을 순차적으로 수행
    - 결과를 `PostSummarized` 이벤트로 발행

- Processor는 MongoDB에 직접 접근하지 않으며, 오직 **입력 이벤트(`PostCreated`) → 출력 이벤트(`PostSummarized`)** 변환만 담당한다.

### 4.2 목표 Processor 파이프라인

목표는 다음과 같은 단순한 구조다.

1. **입력 이벤트**: `PostCreated` 하나만 Processor의 진입점으로 사용

2. **파이프라인 서비스 (개념)**

   - 예: `PostProcessingService`
   - 책임: 하나의 포스트에 대해 다음 단계를 순차적으로 수행

     1. HTML 렌더링 (renderer)
     2. 텍스트 파싱 (parser)
     3. AI 요약 (summarizer / LLM 클라이언트)
     4. 요약/카테고리/태그를 포함한 `PostSummarized` 이벤트 발행

   - MongoDB에 대한 쓰기 책임은 Aggregate에 있으며, Processor는 이벤트 변환에만 집중한다.

3. **이벤트 핸들러의 역할**

   - `HandlePostCreated(ctx, event)`:
     - 이벤트 payload(특히 `Link`)를 사용해 파이프라인을 직접 실행하고, `PostSummarized`를 발행한다.
     - DB에 대한 책임은 갖지 않는다.

4. **출력 이벤트**: `PostSummarized` 하나로 외부에 처리 완료를 알림

> 이렇게 되면 Processor는 "새 포스트가 생성되었다" → "해당 포스트 처리 완료"의 양쪽 끝만 이벤트로 노출하고, 중간 파이프라인은 내부 도메인 로직으로 숨길 수 있다.

---

## 5. 이벤트 경계 재정의

현재 이벤트들을 다음과 같이 분류한다.

| 이벤트 타입              | 생산자    | 소비자                | 성격           | 단순화 방향                          |
| ------------------------ | --------- | --------------------- | -------------- | ------------------------------------ |
| `PostCreated`            | Aggregate | Processor             | 서비스 간 경계 | **유지** (요약 파이프라인 진입점)    |
| `PostSummarized`         | Processor | Aggregate, (미래) RAG | 서비스 간 경계 | **유지** (요약/RAG 인덱서 진입점)    |
| `PostThumbnailRequested` | Aggregate | Processor             | 서비스 간 경계 | **유지** (썸네일 파이프라인 진입점)  |
| `PostThumbnailParsed`    | Processor | Aggregate             | 서비스 간 경계 | **유지** (썸네일 결과 반영용 이벤트) |

과거에는 `PostHTMLFetched`, `PostTextParsed` 와 같은 내부 단계용 이벤트가 존재했으나,
현재는 Processor 내부 파이프라인 로직으로 통합되어 외부에 노출되지 않는다. 썸네일은 별도의
`PostThumbnailRequested` / `PostThumbnailParsed` 이벤트 쌍을 통해서만 비동기 처리된다.

---

## 6. Tidy First 단계 계획 (Aggregate + Processor)

> 여기서는 **행동을 크게 바꾸지 않는 범위**에서 우선 할 수 있는 정리 작업을 정의하고, 그 이후에 적용할 수 있는 구조 변경(리팩터링)을 별도로 구분한다.

### 6.1 1단계: 역할/책임 문서화 (현재 단계)

- Aggregate
  - "RSS 수집 + 신규 포스트 감지 + PostCreated 발행"이 핵심 책임임을 명시.
- Processor
  - "PostCreated를 받아 HTML/텍스트/요약 파이프라인을 끝까지 처리하고, PostSummarized를 발행"하는 것이 핵심 책임임을 명시.
- 내부 이벤트(`PostHTMLFetched`, `PostTextParsed`)는 Processor 내부 구현 디테일이며, 장기적으로 줄이는 방향이라고 선언.

### 6.2 2단계: 코드 레벨 Tidy 후보 (행동 변경 최소)

- **Aggregate 쪽**

  - RSS 수집, DB 저장, 이벤트 발행 책임이 명확히 나뉘어 있는지 확인.
  - 중복 로깅/에러 처리 패턴을 정리(공통 함수 또는 서비스 메서드 수준에서 일관성 확보).

- **Processor 쪽**
  - `EventHandlers`의 의존성과 책임을 명시적으로 정리 (주입되는 것 vs 내부 생성 분리).
  - `processHTMLStep`, `processTextStep`, `processAIStep`에서 공통되는 패턴(포스트 로드, 상태 플래그 업데이트, 에러 로깅 등)을 식별만 해 두기.

> 이 단계에서는 **동작을 바꾸지 않는다.** 오직 코드 구조/의존성/로깅 패턴만 정리하는 수준이다.

### 6.3 3단계: Processor 내부 파이프라인 통합 (행동 변경 수반)

> 이 단계부터는 실제 동작에 영향을 줄 수 있으므로, RAG 도입 일정과 맞춰 따로 계획한다.

- `PostProcessingService` 도입

  - `Run(ctx, postID)` (또는 유사 시그니처) 메서드를 통해 전체 파이프라인을 캡슐화.
  - 기존 `process*Step` 로직을 점진적으로 이 서비스로 이동.

- EventHandlers 단순화

  - `HandlePostCreated`에서만 `PostProcessingService`를 호출하도록 변경.
  - `HandlePostHTMLFetched`, `HandlePostTextParsed`는 점차 사용처를 제거하거나, 내부 리팩터링 후 deprecated 상태로 관리.

- 이벤트 축소
  - 충분한 검증 후, Processor 내부에서 더 이상 `PostHTMLFetched`, `PostTextParsed`가 필요 없게 되면 이벤트 발행을 중단.
  - 이에 따라 `events` 정의, EventBus 사용처를 정리.

### 6.4 4단계: RAG 인덱서와의 연계

- `PostSummarized` 이벤트 구조가 RAG에서 필요한 정보(요약, 태그, 카테고리, 모델명, 생성 시각 등)를 충분히 담고 있는지 검토.
- 필요 시 필드를 확장(예: 언어, 길이 정보 등)하고, 이벤트 버전 관리 전략 명시.

---

## 7. 요약

- Aggregate는 **RSS → 신규 포스트 감지 → PostSummaryRequested(요약 요청) 발행**에 집중한다.
- Processor는 **PostSummaryRequested(요약 요청) → (내부 파이프라인) → PostSummarized**로 요약 흐름을 단순화한다.
- 썸네일은 **PostThumbnailRequested → PostThumbnailParsed** 로 이루어진 별도의 파이프라인에서 처리되며,
  `models.StatusFlags.ThumbnailParsed` 플래그를 통해 진행 여부를 추적한다.
- 중간 단계 이벤트(`PostHTMLFetched`, `PostTextParsed`)는 Processor 내부 상태로 통합하는 방향을 문서로 고정했다.
- 이 설계를 기반으로, 이후 Tidy First 리팩터링과 RAG 인덱서 도입을 단계적으로 진행할 수 있다.
