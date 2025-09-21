#!/usr/bin/env bash
set -euo pipefail

# Build and start all services (mongodb, api, aggregate)
docker compose up -d --build mongodb api aggregate

echo "All services are up. API: http://localhost:8080 (Swagger: /swagger/index.html)"
