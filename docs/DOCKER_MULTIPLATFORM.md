# Multi-Platform 빌드 가이드

## 빌드 방법

### 1. 로컬 개발 (현재 플랫폼)

```bash
# BuildKit 활성화
export DOCKER_BUILDKIT=1

# 현재 플랫폼용 빌드
docker compose build
```

### 2. Multi-Platform 빌드 (arm64 + amd64)

```bash
# buildx 빌더 생성 (1회만)
docker buildx create --name multiplatform --use
docker buildx inspect --bootstrap

# 두 플랫폼 모두 빌드 및 레지스트리 푸시
docker buildx build --platform linux/amd64,linux/arm64 \
  -t your-registry/tech-letter-api:latest \
  -f Dockerfile.api \
  --push .

# 또는 로컬에 로드 (한 플랫폼만 가능)
docker buildx build --platform linux/arm64 \
  -f Dockerfile.api \
  --load \
  -t tech-letter-api:latest .
```

### 3. 특정 플랫폼 지정

```bash
# arm64 전용 빌드
docker build --platform linux/arm64 -f Dockerfile.api -t tech-letter-api:arm64 .

# amd64 전용 빌드
docker build --platform linux/amd64 -f Dockerfile.api -t tech-letter-api:amd64 .
```

## 주요 변경 사항

### Go Dockerfile (api, retryworker)
- `BUILDPLATFORM`: 빌드를 실행하는 플랫폼 (예: linux/amd64)
- `TARGETARCH`, `TARGETOS`: 타겟 플랫폼 (예: arm64, linux)
- Cross-compilation 지원으로 빠른 빌드

### Python Dockerfile (summary_worker)
- `/usr/lib` 전체 복사로 arm64/amd64 모두 지원
- Playwright는 자동으로 플랫폼 감지

## 권장 배포 플로우

**개발 (로컬):**
```bash
docker compose build  # 현재 플랫폼
docker compose up -d
```

**프로덕션 (CI/CD):**
```bash
# GitHub Actions 등에서
docker buildx build --platform linux/arm64 --push ...
```
