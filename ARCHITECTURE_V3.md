# Parsing2026 — Production Architecture V3

## Goals

V3 keeps the latency-sensitive autobuy path small while adding the operational controls found in mature bot systems: deterministic lifecycle management, typed configuration, bounded concurrency, explicit backpressure, observability, persistent schema evolution, reproducible checks, container health, and compatibility with the previous environment naming scheme.

## Boundaries

- main.py — process entry point only.
- app/bootstrap.py — startup, signal handling, health server, maintenance and shutdown.
- app/application.py — composition root and handler registration seam.
- app/runtime/core.py — Telegram/UI runtime state and compatibility helpers.
- app/runtime/health.py — liveness, readiness and Prometheus endpoints.
- app/runtime/tasks.py — background task ownership.
- app/config/settings.py — typed, validated configuration with legacy aliases.
- app/services/market_api.py — shared HTTP session, retries, rate limiting and balance cache.
- app/storage/sqlite.py — SQLite connection, migrations, indexes and retention cleanup.
- market/discovery.py — bounded source discovery with cancellation cleanup.
- market/pipeline.py — discovery -> decision -> queue -> seen state.
- buyer/queue.py — bounded per-user autobuy workers and backpressure.
- purchase/idempotency.py — process-local race prevention with TTL recovery.
- domain/ and filters/ — side-effect-light decision logic.

## Reliability controls

1. Config fails closed by default (ACCESS_MODE=closed).
2. Legacy environment aliases are accepted during migration.
3. All outbound HTTP uses one reusable aiohttp session.
4. 429 responses honor Retry-After; 5xx/408/425 can retry with bounded jitter.
5. Discovery has explicit in-flight limits and cancellation draining.
6. Autobuy queue admission is non-blocking and rejects new work when full.
7. Idempotency claims expire if a task dies without cleanup.
8. SQLite uses WAL, foreign keys, busy timeout and schema migration versioning.
9. Seen/purchase-attempt tables have indexes and periodic retention cleanup.
10. Shutdown cancels owned background tasks, worker pools, network sessions and database connections.
11. /healthz exposes process liveness, /readyz exposes startup readiness, /metrics exposes counters.
12. Logs support plain and JSON output and redact common secret patterns.

## Verification

CI verifies Python 3.12–3.14 on Linux and Windows, then runs compile, pytest, pyflakes and Ruff. A security job runs pip-audit, and a Docker build job verifies the production image definition.

## What is intentionally not added

- No mandatory Redis/PostgreSQL dependency for local Windows operation.
- No separate microservices.
- No synchronous hot-path code.
- No fixed sleeps inserted into the normal autobuy first wave.
- No frontend/dashboard dependency.

The project can adopt PostgreSQL/Redis later behind repository/service interfaces when one-process SQLite is no longer sufficient.
