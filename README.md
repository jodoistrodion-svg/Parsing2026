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

## Android / Termux

A dedicated Android deployment branch is available at `deploy/android-termux`. It targets the realme C35/Android 13 setup and adds Termux bootstrap, runit supervision, boot startup, backups and Android-specific dependency handling without rewriting the application core.

Quick start on the phone:

    git clone --branch deploy/android-termux --single-branch https://github.com/jodoistrodion-svg/Parsing2026.git
    cd Parsing2026
    bash android/proot-bootstrap.sh

The single bootstrap command installs Debian through PRoot-Distro, creates the Linux venv, installs runtime and development dependencies, creates/preserves .env, runs compile/tests/lint, installs the supervised service and creates the Termux:Boot hook. The initial AUTOBUY_MODE is always dry-run.

Install and open Termux:Boot once from the same source family as Termux. The generated boot hook then starts the supervised service automatically.

Check runtime:

    bash android/status.sh

The Android deployment starts with `AUTOBUY_MODE=dry-run`.

## Configuration

Preferred variables:

- API_TOKEN
- OWNER_ID / OWNER_IDS
- LZT_API_KEY (legacy/global fallback only)
- CREDENTIAL_ENCRYPTION_KEY
- ACCESS_MODE=closed
- AUTOBUY_MODE=live

For migration, the loader also accepts TELEGRAM_BOT_TOKEN, BOT_TOKEN, LZT_API_TOKEN and ADMIN_TELEGRAM_ID. An old DRY_RUN=true setting is interpreted as AUTOBUY_MODE=dry-run.

The loader validates configuration before Telegram polling starts.

### Per-user LZT credentials

Customers connect their own LZT API token from **🔑 LZT API** inside Telegram. The token is verified against the LZT API, encrypted with a server-side Fernet key, and bound to the Telegram user ID. Search, balance and autobuy requests use that user credential; balance cache and request rate-limit state are isolated per user. The plaintext token is never stored in SQLite or shown in the admin UI.

Generate `CREDENTIAL_ENCRYPTION_KEY` once with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and keep it outside Git. Losing this key makes encrypted customer credentials unrecoverable; rotate it only with an explicit credential re-encryption migration.

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
