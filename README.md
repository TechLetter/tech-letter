
# Tech-Letter

여러 기술 블로그의 최신 포스팅을 요약하여 뉴스레터 형식으로 제공하는 서비스

## 아키텍처

### 이벤트 기반 마이크로서비스 구조

- **API 서버** (`cmd/api/main.go`): REST API 제공 (포트 8080)
- **Aggregate 서버** (`cmd/aggregate/main.go`): 기존 동기식 처리 (레거시)
- **Aggregate-Event 서버** (`cmd/aggregate-event/main.go`): 이벤트 기반 비동기 처리 (신규)

### 기술 스택

- **언어**: Go 1.25.1
- **웹 프레임워크**: Gin
- **데이터베이스**: MongoDB
- **메시지 큐**: Apache Kafka
- **AI**: Google Gemini API
- **컨테이너**: Docker & Docker Compose

### 이벤트 플로우

1. **포스트 수집**: RSS 피드에서 새 포스트 발견 → `PostCreated` 이벤트 발행
2. **HTML 렌더링**: 포스트 HTML 렌더링 완료 → `PostHTMLFetched` 이벤트 발행
3. **텍스트 파싱**: HTML에서 텍스트 추출 완료 → `PostTextParsed` 이벤트 발행
4. **AI 요약**: Gemini API로 요약 완료 → `PostSummarized` 이벤트 발행

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