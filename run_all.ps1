# Build and start all services
docker compose up -d --build mongodb api aggregate

Write-Host "All services are up. API: http://localhost:8080 (Swagger: /swagger/index.html)" -ForegroundColor Green
