# Changelog

## Unreleased — Production V3

- Added typed runtime settings with legacy environment aliases.
- Added fail-closed configuration validation and LZT API host validation.
- Added liveness, readiness and Prometheus-compatible metrics endpoints.
- Added deterministic background-task ownership and shutdown.
- Added explicit autobuy queue backpressure metrics and queue snapshots.
- Added idempotency claim TTL recovery.
- Added server-aware Retry-After handling and bounded HTTP retries.
- Added SQLite schema versioning, additional indexes and retention cleanup.
- Added Linux/Windows Python 3.12–3.14 CI, Ruff, pip-audit and Docker build verification.
- Added production Docker and compose definitions.
- Added security and contributor documentation.
