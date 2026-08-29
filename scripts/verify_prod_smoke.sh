#!/usr/bin/env bash
# 배포 직후 스모크. 실패하면 배포 워크플로가 롤백한다.
#
# 컨테이너 healthcheck 는 "프로세스가 살아 있는가" 만 본다. 여기서는
# "요청이 실제로 처리되는가" 를 본다 — 그 둘이 갈라진 적이 있다.
set -euo pipefail

API="${SMOKE_API_URL:-http://localhost:8080}"
NETWORK="${SMOKE_NETWORK:-tech-letter_default}"

# 러너 호스트에서 API 포트가 열려 있지 않다. 같은 네트워크에서 친다.
curl_in_network() {
  docker run --rm --network "$NETWORK" curlimages/curl:latest -sS -m 10 "$@"
}

fail() { echo "::error::$1"; exit 1; }

echo "1/5 헬스체크"
health=$(curl_in_network "$API/health") || fail "health 요청 실패"
echo "$health" | grep -q '"status":"ok"' || fail "health 가 ok 가 아니다: $health"

echo "2/5 포스트 목록 (봉투 확인)"
posts=$(curl_in_network "$API/api/v1/posts?page_size=1") || fail "posts 요청 실패"
for key in items page page_size total total_pages; do
  echo "$posts" | grep -q "\"$key\"" || fail "posts 응답에 $key 가 없다"
done

echo "3/5 인증 필요 경로가 401 을 낸다"
code=$(curl_in_network -o /dev/null -w '%{http_code}' "$API/api/v1/me") || true
[ "$code" = "401" ] || fail "GET /me 가 401 이 아니라 $code 를 냈다"

echo "4/5 에러 봉투"
missing=$(curl_in_network "$API/api/v1/posts/507f1f77bcf86cd799439011") || true
echo "$missing" | grep -q '"code":"resource.not_found"' \
  || fail "404 가 계약 봉투를 쓰지 않는다: $missing"

echo "5/5 워커가 살아 있다"
for name in techletter_worker techletter_summary_worker techletter_embedding_worker; do
  status=$(docker inspect "$name" --format '{{.State.Health.Status}}' 2>/dev/null || echo missing)
  [ "$status" = "healthy" ] || fail "$name 상태가 $status 다"
done

echo "스모크 통과"
