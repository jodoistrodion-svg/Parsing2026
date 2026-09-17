# Parsing2026 — Refactor V2

Telegram LZT Market bot with a latency-sensitive autobuy path.

## Configuration

1. Copy `.env.example` to `.env`.
2. Set `API_TOKEN` and `LZT_API_KEY`.
3. Optional runtime settings can be supplied through environment variables or `config.py`.

## Architecture

The hot path is kept intentionally short:

`discover -> cheap dedup/decision -> queue -> concurrent purchase first wave`

The no-account-check path does not add a mandatory validation request or fixed sleep. The legacy `_try_autobuy_once()` runner remains behind the `purchase/` seam.

Packages:

- `bot/` — autobuy endpoint strategy and UI helpers
- `buyer/` — per-user concurrent queue
- `domain/` — pure models and decisions
- `filters/` — synchronous filters
- `market/` — discovery, URL normalization, rate state
- `purchase/` — purchase seam and idempotency
- `runtime/` — runtime state
- `storage/` — persistence protocols
- `metrics/` — latency primitives
- `services/` — infrastructure helpers

`main.py` remains the compatibility shell during incremental migration.

## Tests

The GitHub Actions workflow is in `.github/workflows/tests.yml` and runs `PYTHONPATH=. pytest -q` on Python 3.11.
