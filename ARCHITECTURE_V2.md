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

## Production-audit hardening

- Runtime configuration is loaded and type-validated in `app/config/settings.py`; `config.py` is only a compatibility facade.
- Telegram handlers use explicit runtime imports; URL/user pagination constants are not implicit globals.
- Market URL normalization uses parsed query parameters and a canonical host allowlist instead of substring rewriting.
- Balance caching is owned by the market API service and exposes an explicit invalidation operation.
- Autobuy queue admission is explicit: a full queue rejects a new job instead of silently dropping older jobs.
- A rejected autobuy queue handoff does not mark the item as seen.
- Purchase idempotency claims can only be released by their owning task.
- Missing LZT API credentials fail the autobuy attempt immediately rather than entering a pointless retry window.
- Development test dependencies live in `requirements-dev.txt`; CI installs both runtime and development requirements.
