# Parsing2026

Асинхронный Telegram-бот для мониторинга источников LZT Market и обработки автобая.

## Production architecture

Проект построен вокруг одного асинхронного процесса:

    Telegram
       │
       ▼
    aiogram handlers
       │
       ▼
    runtime / state
       │
       ├── market discovery -> decision/filter
       │                          │
       │                          ▼
       │                    bounded queue
       │                          │
       │                          ▼
       │                     autobuy engine
       │                          │
       │                          ▼
       │                       LZT API
       │
       ├── SQLite repositories
       ├── health/readiness
       └── metrics/logging

The latency-sensitive path stays inside one process and uses bounded async concurrency. Operational infrastructure is optional and can be enabled through environment variables.

## Windows setup

The recommended local layout is a persistent Git checkout, not repeated ZIP extraction.

    D:\Parsing\lzt_market_bot

One-time installation:

    cd "D:\Parsing\lzt_market_bot"
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

Create .env once. Future code updates do not overwrite it.

Update code:

    git pull --ff-only origin main

Run:

    .\.venv\Scripts\python.exe main.py

## Configuration

Preferred variables:

- API_TOKEN
- OWNER_ID / OWNER_IDS
- LZT_API_KEY
- ACCESS_MODE=closed
- AUTOBUY_MODE=live

For migration, the loader also accepts TELEGRAM_BOT_TOKEN, BOT_TOKEN, LZT_API_TOKEN and ADMIN_TELEGRAM_ID. An old DRY_RUN=true setting is interpreted as AUTOBUY_MODE=dry-run.

The loader validates configuration before Telegram polling starts.

## Commercial access

The bot supports owner-managed one-time access codes. Customers can redeem a code from Telegram; redemption is atomically bound to their Telegram user ID, and the plaintext code is not stored in SQLite.

The owner can use **🔑 Коды доступа** to generate codes, inspect license statistics and revoke access by Telegram ID.

See [COMMERCIAL_ACCESS.md](COMMERCIAL_ACCESS.md) for the commercial deployment checklist. Payment processing is intentionally separate from the licensing layer.

## Health and metrics

Set HEALTH_PORT=8080 to expose:

- GET /healthz — process liveness.
- GET /readyz — startup readiness.
- GET /metrics — Prometheus-compatible counters/gauges.

For Docker, docker compose up --build publishes port 8080 and stores SQLite in ./data.

## Verification

    python -m compileall -q .
    python -m pytest -q
    python -m pyflakes .
    python -m ruff check .
    python -m pip_audit -r requirements.txt

GitHub Actions runs the test/lint matrix on Python 3.12, 3.13 and 3.14 for Linux and Windows, plus dependency audit and Docker build.

## Security

Never commit .env, tokens, secret answers, databases or logs.

The current repository intentionally contains only placeholders in env.example. Any credentials exposed in older history must be revoked and replaced at the provider.
