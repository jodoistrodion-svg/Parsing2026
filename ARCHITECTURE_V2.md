# Refactor V2

## Latency contract

The autobuy hot path remains: discover -> cheap dedup/decision -> non-blocking queue -> concurrent purchase first wave -> cancel losing requests. The no-account-check path adds no mandatory validation request and no fixed sleep.

## Boundaries

- `domain/`: market/purchase models and pure decisions.
- `filters/`: cheap synchronous filters.
- `market/`: discovery orchestration, URL normalization and adaptive server-header rate state.
- `purchase/`: purchase seam and per-item idempotency.
- `buyer/`: concurrent per-user dispatch.
- `storage/`: persistence protocols.
- `runtime/`: runtime state model.
- `metrics/`: latency primitives.

`main.py` stays as a compatibility shell while hot-path behavior is migrated incrementally.
