#!/usr/bin/env bash
set -euo pipefail

docker compose up -d --build mongodb api

echo "API is running at http://localhost:8080"
