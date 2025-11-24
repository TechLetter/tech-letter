# Processor 서비스 Tidy First 계획

## 1. 배경

Tech-Letter는 현재 다음과 같은 이벤트 기반 아키텍처를 사용하고 있다.

- Aggregate 서버: RSS 수집 → `PostSummaryRequested`(요약 요청) 이벤트 발행
- Processor 서버: 이벤트를 구독하여 HTML 렌더링, 텍스트 파싱, AI 요약 수행
- EventBus: Kafka 기반, `eventbus.EventBus` 인터페이스를 통해 추상화

RAG 기반 챗봇을 도입하기 전에, Processor 내부 구조가 **과도하게 이벤트 중심으로 쪼개져 있어** 이해/확장/테스트 난이도가 높다. Kent Beck의 _Tidy First_ 원칙에 따라, 새로운 기능을 넣기 전에 **행동(동작)을 바꾸지 않는 작은 정리 작업들**부터 계획한다.

이 문서는 Processor 내부를 단순화하기 위한 Tidy First 계획을 정리한다.

---

## 2. 현재 Processor 구조 요약

### 2.1 엔트리포인트

- 파일: `cmd/processor/main.go`
- 역할:
  - `config.InitApp()`, `config.InitLogger()` 호출
  - `db.Init(ctx)` 로 MongoDB 초기화
  - `eventbus.GetBrokers()`, `eventbus.EnsureTopics`, `eventbus.NewKafkaEventBus` 로 EventBus 초기화
  - `bus.Subscribe(...)` 로 `TopicPostEvents` 구독
  - Kafka 메시지를 JSON으로 디코딩한 후 `events.BaseEvent.Type` 에 따라 **switch** 수행
  - 각 타입별로 `handlers.EventHandlers` 의 핸들러 메서드 호출
  - `bus.StartRetryReinjector(...)` 로 retry 토픽 재주입기 실행

### 2.2 이벤트 핸들러 레이어

- 파일: `cmd/processor/handlers/event_handlers.go`
- 주요 구조체: `EventHandlers`

  - 필드:
    - `eventService *eventServices.EventService`
  - 생성자: `NewEventHandlers(eventService *eventServices.EventService)`

- 주요 메서드 (현재 구현 기준):

  - `HandlePostSummaryRequested`
    - `PostSummaryRequested` 이벤트를 받아 HTML 렌더링 → 텍스트 파싱 → AI 요약을 한 번에 수행
    - 결과를 `PostSummarized` 이벤트로 발행 (DB에는 직접 쓰지 않음)
  - `HandlePostThumbnailRequested`
    - `PostThumbnailRequested` 이벤트를 받아 HTML 렌더링 → 썸네일 파싱만 수행
    - 결과를 `PostThumbnailParsed` 이벤트로 발행 (썸네일 전용 파이프라인)

과거에는 `HandlePostHTMLFetched`, `HandlePostTextParsed` 등의 중간 단계용 핸들러와
`process*Step` 헬퍼들이 존재했지만, 현재는 모두 제거되었고 파이프라인이 단일 핸들러로 통합되었다.

### 2.3 이벤트 발행 서비스 레이어

- 파일: `cmd/processor/services/event_service.go`
- 구조체: `EventService`
  - 필드: `bus eventbus.EventBus`
  - 책임: Processor에서 발생한 도메인 이벤트를 EventBus를 통해 발행
- 주요 메서드 (현재 구현 기준):
  - `PublishPostSummarized` (HTML/텍스트/요약 처리 결과를 `PostSummarized` 이벤트로 발행)
  - `PublishPostThumbnailParsed` (썸네일 파싱 결과를 `PostThumbnailParsed` 이벤트로 발행)

### 2.4 Summarizer (LLM 호출)

- 파일: `cmd/processor/summarizer/summarizer.go`
- 주요 특징:
  - `SummarizeText(text string)` 내부에서 **직접** Gemini SDK(`genai`)를 사용
  - `GEMINI_API_KEY` 환경 변수와 `config.GetConfig().GeminiModel` 을 직접 참조
  - 모델 응답을 `SummarizeResult` 구조체로 파싱, `LLMRequestLog` 로 로깅 정보 구성

---

## 3. Processor 내부의 문제점 (Tidy 대상)

1. **서비스 내부까지 과도한 이벤트 사용 (과거 구조)**

   - 과거에는 `PostCreated → PostHTMLFetched → PostTextParsed → PostSummarized` 순서가 모두 동일한 Processor 프로세스 안에서 처리되면서, 각 단계를 이벤트로 연결하고 있었다.
   - 현재는 리팩터링을 통해 **외부에 노출되는 이벤트를 `PostSummaryRequested`와 `PostSummarized` 두 가지로 줄이고**, HTML/텍스트/요약 단계는 단일 핸들러 내부 로직으로 통합되었다.

2. **EventHandlers의 과도한 책임**

   - DB 접근(PostRepository), HTML 렌더링, 텍스트 파싱, LLM 요약 호출, 상태 플래그 업데이트, 이벤트 발행까지 한 곳에서 모두 조율한다.
   - SRP 관점에서 한 타입이 너무 많은 역할을 갖고 있다.

3. **파이프라인의 전체 그림을 한 곳에서 볼 수 없음**

   - "한 포스트를 처음부터 끝까지 어떻게 처리하는가"에 대한 로직이 여러 함수와 이벤트를 따라가야만 이해된다.
   - RAG 인덱서를 도입할 때, 어느 지점을 기준으로 구독/처리를 시작해야 할지 직관적으로 파악하기 어렵다.

4. **LLM 의존성 경계 부족**
   - summarizer가 Gemini SDK와 환경 변수를 직접 사용하는 구조라, 나중에 OpenAI/Ollama 등 추가 시 변경 범위가 넓어질 수 있다.
   - 이 부분은 RAG에서도 공통으로 필요한 LLM/Embedding 추상화와 직결된다.

---

## 4. 목표 구조 (행동은 유지, 구조만 단순화)

Processor 내부를 다음과 같은 그림으로 단순화하는 것을 목표로 한다.

### 4.1 포스트 처리 파이프라인 서비스 도입

- 개념적인 서비스(예: `PostProcessingService`)를 도입하여 "한 포스트 처리"의 전체 단계를 책임지게 한다.
- 책임:
  - 포스트 로딩 (PostRepository 사용)
  - HTML 렌더링 단계 수행
  - 텍스트 파싱 단계 수행
  - AI 요약 단계 수행
  - 상태 플래그 업데이트 및 요약 저장
  - 최종적으로 `PostSummarized` 이벤트 발행
- 이 서비스는 Processor 내부에서만 사용되며, 외부에는 노출되지 않는 도메인 서비스로 본다.

### 4.2 이벤트 핸들러의 역할 축소

- `EventHandlers`의 역할을 "이벤트 → 파이프라인 서비스 호출"로 한정한다.
  - `HandlePostSummaryRequested(ctx, event)`:
    - 포스트 ID를 추출하고, PostProcessingService에 전달하여 전체 파이프라인을 실행시키는 진입점 역할만 한다.
  - `HandlePostHTMLFetched`, `HandlePostTextParsed` 는 장기적으로는 축소 또는 제거 대상이며, 현재는 기존 이벤트 플로우를 깨지 않는 선에서 유지/정리 전략을 세운다.

### 4.3 외부 서비스 경계에 해당하는 이벤트만 남기기

- **유지할 이벤트 경계(후보)**
  - Aggregate → Processor: `PostSummaryRequested`
  - Processor → (미래) RAG Indexer: `PostSummarized`
- **내부 단계 이벤트는 장기적으로 축소 대상**
  - `PostHTMLFetched`, `PostTextParsed` 는 동일 Processor 내 파이프라인 단계로 간주하고, 향후에는 내부 함수 호출의 결과로 대체 가능하도록 설계 방향을 잡는다.

### 4.4 LLM 의존성의 간접화(향후 Tidy 연결점)

- Summarizer는 LLM 클라이언트 추상화(예: `LLMClient`)만 의존하도록 하는 것을 장기 목표로 한다.
- 이번 Tidy First 계획에서는 **즉시 구현하지 않고**, 구조/책임만 문서로 명시해 둔다.
- RAG 도입 시, 동일한 LLM/Embedding 추상화를 재사용할 수 있도록 한다.

---

## 5. Tidy First 단계별 계획 (행동 변경 최소)

> 아래 단계들은 "가능한 한 행동을 바꾸지 않고" 구조를 다듬기 위한 것이다. 실제 코드 변경은 이 계획을 기준으로 순차적으로 진행한다.

### 5.1 1단계: 개념 경계 문서화 및 합의

- `PostProcessingService` (가칭)의 개념과 책임을 문서로 명확히 정의한다.
  - 이 문서(현재 파일)에 그 역할을 명시 (완료).
- `EventHandlers`는 장기적으로 "이벤트 → 서비스 호출"만 담당하는 어댑터가 되는 것을 목표로 한다는 점을 합의한다.

### 5.2 2단계: 파이프라인 단계 책임 재정의 (설계 수준)

- 현재 `processHTMLStep`, `processTextStep`, `processAIStep` 가 수행하는 일을 다음 두 축으로 나누어 설계한다.
  - 순수 처리 로직
    - HTML 렌더링 및 파싱, 요약 생성 등 I/O 성격이 있지만, 도메인 관점에서의 처리 파이프라인
  - 상태/사이드 이펙트
    - DB 상태 플래그 업데이트, 요약 저장, 이벤트 발행
- 설계 목표:
  - 향후 `PostProcessingService` 내에서 `Run(ctx, postID)` 같은 메서드가 위 과정을 순차적으로 수행할 수 있도록, 단계별 책임을 식별한다.

### 5.3 3단계: 이벤트 경계 역할 정리 (논리적 분류)

> 현재 이벤트의 역할은 다음과 같다.

| 이벤트 타입              | 생산자    | 소비자                | 성격           |
| ------------------------ | --------- | --------------------- | -------------- |
| `PostSummaryRequested`   | Aggregate | Processor             | 서비스 간 경계 |
| `PostSummarized`         | Processor | Aggregate, (미래) RAG | 서비스 간 경계 |
| `PostThumbnailRequested` | Aggregate | Processor             | 서비스 간 경계 |
| `PostThumbnailParsed`    | Processor | Aggregate             | 서비스 간 경계 |

과거에는 `PostHTMLFetched`, `PostTextParsed` 와 같은 내부 단계용 이벤트가 존재했으나,
현재는 Processor 내부 파이프라인 로직으로 통합되어 외부에 노출되지 않는다. 썸네일은
전용 이벤트(`PostThumbnailRequested`, `PostThumbnailParsed`)를 통해 별도 파이프라인으로 처리된다.

### 5.4 4단계: 향후 구조 변경을 위한 사전 작업

> 이 단계는 실제 코드 변경을 수반하므로, RAG 도입과의 우선순위를 고려해서 따로 실행 시점을 정한다.

- 후보 작업들:
  - `PostProcessingService` 타입 추가 및 기존 `process*Step` 로직 점진적 이관
  - EventHandlers에서 renderer/parser/summarizer 직접 호출 대신, 파이프라인 서비스 의존으로 변경
  - 내부 이벤트(`PostHTMLFetched`, `PostTextParsed`) 활용 패턴을 점진적으로 함수 호출로 대체

이 문서는 "어디까지가 Tidy First(행동 변경 최소)"이고, "어디서부터는 동작에 영향을 줄 수 있는 리팩터링인지"를 구분하기 위한 기준선 역할을 한다.

---

## 6. RAG 도입과의 연계

- RAG 인덱서 서비스는 `PostSummarized` 이벤트를 구독하여, 요약이 완료된 포스트를 인덱싱하는 역할을 맡게 된다.
- 따라서 Processor 내부 Tidy First의 핵심 포인트는:
  - **`PostSummarized` 이벤트를 신뢰할 수 있는 단일 진입점으로 유지**하는 것
  - 파이프라인 로직이 한 서비스에 모여 있어, RAG에서 필요한 추가 정보(예: 요약, 태그, 카테고리)를 쉽게 확장/참조할 수 있도록 하는 것이다.
- Processor 내부의 파이프라인이 단순해질수록, RAG 인덱서의 설계도 더 단순해지고, 이벤트/도메인 모델의 책임이 명확해진다.

---

## 7. 정리

- 현재 Processor는 내부 단계까지 이벤트로 쪼개져 있어 구조적 복잡도가 높다.
- Tidy First 관점에서, 먼저 **개념 경계(파이프라인 서비스, 이벤트 역할)** 를 정리하고 문서화했다.
- 이후 실제 코드 리팩터링 시에는 이 문서를 기준으로:
  - Handler의 책임 축소
  - 파이프라인 서비스 도입
  - 내부 이벤트 축소
    등을 단계적으로 수행할 수 있다.
