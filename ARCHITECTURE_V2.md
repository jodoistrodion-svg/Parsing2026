# Refactor V2

## Latency contract

The autobuy hot path remains:

`discover -> cheap dedup/decision -> non-blocking queue -> concurrent purchase first wave -> cancel losing requests`

The no-account-check path adds no mandatory validation request and no fixed sleep. `_try_autobuy_once()` remains the latency-sensitive legacy runner; the new `purchase/` boundary wraps it without adding work.

## Boundaries

- `domain/`: market/purchase models and pure decisions.
- `filters/`: cheap synchronous filters.
- `market/`: discovery orchestration, URL normalization and adaptive server-header rate state.
- `purchase/`: purchase seam and per-item idempotency.
- `buyer/`: concurrent per-user dispatch.
- `storage/`: persistence protocols.
- `runtime/`: runtime state model.
- `metrics/`: latency primitives.
- `bot/`: compatibility exports for autobuy strategy and UI helpers.
- `services/`: infrastructure helpers such as logging.

`main.py` stays as a compatibility shell while hot-path behavior is migrated incrementally.

## Current integration

`hunter_loop_for_user()` constructs `DiscoveryPipeline` per cycle. Autobuy sources are fetched as the first concurrent wave; plain sources are only fetched when their cycle is due. The pipeline performs cheap in-memory dedup/decision before handing an autobuy lot to `UserAutobuyQueueManager`. Persistence is performed after a successful queue handoff so a failed handoff does not permanently hide the lot.

The repository now contains real Python package boundaries matching these imports. The previous flattened `__init__ (N).py` files are left untouched for compatibility/history, but runtime imports use the named packages above.

## Rate-limit behavior

`AdaptiveRateLimiter` is header-driven. It waits only when a bucket reports `X-RateLimit-Remaining: 0` together with an absolute `X-RateLimit-Reset` timestamp. Available quota adds no artificial delay.

## Validation

The V2 test suite covers filters/decision, URL normalization, idempotency, rate-limit no-wait behavior, concurrent autobuy discovery, and queue-before-seen persistence semantics.
