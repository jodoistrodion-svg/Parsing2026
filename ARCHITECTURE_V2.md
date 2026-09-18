# Parsing2026 Architecture

## Composition

- `main.py` is the process entry point only.
- `app/bootstrap.py` owns startup and shutdown lifecycle.
- `app/application.py` is the composition root; it wires runtime core, autobuy and Telegram handlers.
- `app/runtime/core.py` contains application state and orchestration helpers and has no dependency on handlers/autobuy.
- `app/handlers.py` contains Telegram transport handlers and depends on explicit runtime/storage/API services.
- `app/purchase/autobuy.py` owns the autobuy hot path and lifecycle cleanup.

## Infrastructure boundaries

- `app/services/market_api.py` owns HTTP sessions, retries and API rate state; it does not import the application root.
- `app/storage/sqlite.py` owns persistence; it does not import the application root.
- `market/discovery.py` provides bounded concurrent discovery with cancellation cleanup.
- `market/normalize.py` owns market URL validation/normalization.
- `purchase/idempotency.py` provides process-local per-item race prevention.
- `buyer/queue.py` provides bounded per-user autobuy workers.
- `domain/` and `filters/` remain side-effect-light decision/filter layers.

## Latency contract

The autobuy hot path remains: discover -> cheap dedup/decision -> non-blocking queue -> concurrent purchase first wave -> cancel losing requests. The no-account-check path does not add a mandatory validation request or fixed sleep. Existing ~2.8s per-attempt and 6s total retry-window limits remain configurable.

## Verification contract

CI runs Python 3.12, installs the pinned aiogram dependency, compiles every Python file and executes the regression suite. The suite also checks import boundaries, queue shutdown, discovery cancellation, runtime cleanup and dependency alignment.
