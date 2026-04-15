# product-search

Product search and recommendations service

## Tech Stack
- **Language**: python
- **Team**: discovery
- **Platform**: Walmart Global K8s

## Quick Start
```bash
docker build -t product-search:latest .
docker run -p 8080:8080 product-search:latest
curl http://localhost:8080/health
```

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /ready | Readiness probe |
| GET | /metrics | Prometheus metrics |
# PR 1 - 2026-04-15T18:48:59
