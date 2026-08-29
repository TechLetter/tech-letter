.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install dev api lint format typecheck test test-all snapshot check clean

help: ## 사용 가능한 타깃을 보여준다
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## 의존성 설치 (락파일 기준)
	$(UV) sync --frozen

dev: ## 개발용 인프라 기동 (mongo, qdrant)
	docker compose -f docker/compose.dev.yml up -d mongo qdrant

api: ## API 서버 기동 (자동 재시작)
	$(UV) run techletter api --reload

lint: ## ruff 검사
	$(UV) run ruff check src tests scripts
	$(UV) run ruff format --check src tests scripts

format: ## ruff 자동 수정 + 포맷
	$(UV) run ruff check --fix src tests scripts
	$(UV) run ruff format src tests scripts

typecheck: ## pyright
	$(UV) run pyright

test: ## 단위 + 계약 테스트 (컨테이너 불필요)
	$(UV) run pytest -q

test-all: ## 통합·E2E 포함 전체
	$(UV) run pytest -q -m ""

snapshot: ## 현행 API 골든 스냅샷 재캡처 (BASE_URL/TOKEN 필요)
	$(UV) run python scripts/contract_snapshot.py --out tests/contract/snapshots/current

check: lint typecheck test ## CI가 도는 것과 같은 검사

clean: ## 캐시 정리
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
