#!/usr/bin/env bash
#   ./scripts/dev.sh <command>
set -euo pipefail
cd "$(dirname "$0")/.."

UV="${UV:-uv}"

cmd_install() { # 의존성 설치 (락파일 기준)
  "$UV" sync --frozen
}

cmd_dev() { # 개발용 인프라 기동 (mongo, qdrant)
  docker compose -f docker/compose.dev.yml up -d mongo qdrant
}

cmd_api() { # API 서버 기동 (자동 재시작)
  "$UV" run techletter api --reload
}

cmd_lint() { # ruff 검사
  "$UV" run ruff check src tests scripts
  "$UV" run ruff format --check src tests scripts
}

cmd_format() { # ruff 자동 수정 + 포맷
  "$UV" run ruff check --fix src tests scripts
  "$UV" run ruff format src tests scripts
}

cmd_typecheck() { # pyright
  "$UV" run pyright
}

cmd_test() { # 단위 + 계약 테스트 (컨테이너 불필요)
  "$UV" run pytest -q
}

cmd_test-all() { # 통합·E2E 포함 전체
  "$UV" run pytest -q -m ""
}

cmd_snapshot() { # 현행 API 골든 스냅샷 재캡처 (BASE_URL/TOKEN 필요)
  "$UV" run python scripts/contract_snapshot.py --out tests/contract/snapshots/current
}

cmd_check() { # CI가 도는 것과 같은 검사
  cmd_lint
  cmd_typecheck
  cmd_test
}

cmd_clean() { # 캐시 정리
  find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
  rm -rf .pytest_cache .ruff_cache
}

cmd_help() { # 사용 가능한 명령을 보여준다
  echo "사용법: ./scripts/dev.sh <command>"
  echo
  grep -E '^cmd_[a-zA-Z_-]+\(\) \{ #' "$0" | sed -E 's/^cmd_([a-zA-Z_-]+)\(\) \{ # (.*)/\1\t\2/' \
    | awk -F'\t' '{printf "  %-12s %s\n", $1, $2}'
}

sub="${1:-help}"
shift || true
if declare -f "cmd_${sub}" >/dev/null; then
  "cmd_${sub}" "$@"
else
  echo "알 수 없는 명령: ${sub}" >&2
  cmd_help
  exit 1
fi
