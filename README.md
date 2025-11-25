# Tech-Letter

여러 기술 블로그의 최신 포스팅을 요약하여 뉴스레터 형식으로 제공하는 서비스

### 기술 스택

- **언어**: Go 1.25.1
- **웹 프레임워크**: Gin
- **데이터베이스**: MongoDB
- **메시지 큐**: Apache Kafka
- **AI**: Google Gemini API
- **컨테이너**: Docker & Docker Compose

## 아키텍처

### 마이크로서비스 구조

- **API 서버** (`cmd/api/main.go`): REST API 제공 (포트 8080)
- **Aggregate 서버** (`cmd/aggregate/main.go`):
  - RSS 수집 및 신규 포스트 MongoDB 저장
  - 신규 포스트에 대해 `PostCreated` 이벤트 발행
  - `PostSummarized` 이벤트를 구독해 요약/렌더링/썸네일 결과를 DB에 반영
- **Processor 서버** (`cmd/processor/main.go`):
  - `PostCreated` 이벤트를 구독해 HTML 렌더링 → 텍스트 파싱 → 썸네일 추출 → AI 요약 수행
  - 결과를 담은 `PostSummarized` 이벤트 발행 (DB에는 직접 쓰지 않음)
- **Retry Worker** (`cmd/retryworker/main.go`):
  - `eventbus` 레이어가 생성한 지연/재시도 토픽(`*.retry.N`)을 구독
  - 지연 시간이 지난 이벤트를 다시 기본 토픽으로 재주입하여 재시도 처리
  - 최대 재시도 횟수 초과 시 DLQ 토픽으로 이동

#### Architecture Diagram (Component View)

```mermaid
flowchart LR
    Client[User / Frontend] --> API[API Server]
    API --> EB[EventBus / Kafka]

    subgraph Services
        Agg[Aggregate]
        Proc[Processor]
        RW[Retry Worker]
    end

    Agg --> EB
    Proc --> EB
    RW --> EB

    Agg --> DB[(MongoDB)]
    Proc --> LLM[Gemini API]
```

### 이벤트 플로우

1. **포스트 수집 (Aggregate)**  
   RSS 피드에서 새 포스트 발견 → MongoDB에 새 포스트 저장  
   `status.ai_summarized=false` 로 초기화 후 `PostCreated` 이벤트 발행 (`tech-letter.post.events` 토픽)

2. **요약 + 썸네일 파이프라인 (Processor)**

   - `PostCreated` 이벤트를 구독
   - HTML 렌더링 → 텍스트 파싱 → 썸네일 추출 → Gemini 요약 수행
   - 렌더링된 HTML, 썸네일 URL, 요약 결과를 포함한 `PostSummarized` 이벤트 발행 (`tech-letter.post.events`)

3. **결과 DB 반영 (Aggregate)**

   - `PostSummarized` 이벤트를 구독
   - `posts.aisummary`, `posts.thumbnail_url`, `posts.rendered_html` 업데이트
   - `status.ai_summarized = true` 로 상태 플래그 갱신

4. **실패 시 재시도 (EventBus + Retry Worker)**

   - Processor 또는 Aggregate에서 이벤트 처리 실패 시, `eventbus` 레이어가 재시도 토픽(`tech-letter.post.events.retry.N`)으로 이벤트를 이동
   - Retry Worker가 지연 시간이 지난 메시지를 다시 기본 토픽(`tech-letter.post.events`)으로 재주입
   - 최대 재시도 횟수를 초과하면 DLQ 토픽(`tech-letter.post.events.dlq`)으로 이동하여 후속 수동 처리

#### Event Flow Diagram

```mermaid
sequenceDiagram
    participant Agg as Aggregate
    participant Proc as Processor
    participant RW as RetryWorker
    participant EB as EventBus/Kafka
    participant DB as MongoDB

    Agg->>DB: Insert new Post (status.ai_summarized=false)
    Agg->>EB: PostCreated (tech-letter.post.events)
    EB->>Proc: Deliver PostCreated
    Proc->>Proc: RenderHTML + ParseText + ParseThumbnail + Summarize
    Proc->>EB: PostSummarized (tech-letter.post.events)
    EB->>Agg: Deliver PostSummarized
    Agg->>DB: Update aisummary + rendered_html + thumbnail_url + status.ai_summarized=true

    alt Handler error (Processor or Aggregate)
        EB->>EB: Publish to retry topic (tech-letter.post.events.retry.N)
        RW->>EB: After delay, re-publish to base topic
        EB->>Proc: or Agg: Redeliver event
    end
```

## 개발 가이드

### Swagger 문서 업데이트

```sh
swag init -g cmd/api/main.go -o docs
```

### Docker Compose 실행

```sh
# Kafka 및 MongoDB 실행 (별도 프로젝트)
docker network create tech-letter_default

# Tech-Letter 서비스 실행
docker-compose up -d
```

### 환경 변수 설정

`.env` 파일을 생성하고 `.env.example`을 참고하여 설정

### Kafka 토픽

- `tech-letter.post.events`: 포스트 관련 이벤트
- `tech-letter.newsletter.events`: 뉴스레터 관련 이벤트 (Phase 2)

## 서비스 포트

- API 서버: 8080
- Kafka UI: 8081
- Kafka: 9092
