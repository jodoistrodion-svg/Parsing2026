import asyncio
import time

from bot.autobuy_strategy import build_buy_urls
from market.rate_limit import AdaptiveRateLimiter


def test_autobuy_strategy_uses_only_documented_fast_buy_routes():
    urls = build_buy_urls("https://api.lzt.market/mihoyo?order_by=pdate_to_down", 123)
    assert urls == ["https://api.lzt.market/123/fast-buy"]
    assert all("/buy" not in url.removeprefix("https://").split("/", 1)[-1] for url in urls)


def test_autobuy_strategy_never_inherits_an_untrusted_source_host():
    urls = build_buy_urls("https://example.invalid/mihoyo", 123)
    assert urls == ["https://api.lzt.market/123/fast-buy"]


def test_default_lzt_pacing_matches_documented_base_and_search_limits():
    from app.config import settings

    assert settings.SEARCH_MIN_REQUEST_INTERVAL == 3.0
    assert settings.OTHER_MIN_REQUEST_INTERVAL == 0.2
    assert settings.BUY_MIN_REQUEST_INTERVAL == 0.2
    assert settings.AUTOBUY_PARALLEL_HTTP == 1
    assert settings.AUTOBUY_BURST_FIRST_WAVE == 1
    assert settings.AUTOBUY_MAX_HTTP_ATTEMPTS == 2


def test_adaptive_limiter_waits_until_server_reset_after_quota_exhaustion():
    async def run():
        limiter = AdaptiveRateLimiter(safety_ms=0)
        await limiter.observe(
            "user:1:search-global",
            {
                "X-RateLimit-Limit": "20",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(time.time() + 0.05),
            },
        )
        started = time.perf_counter()
        await limiter.before_request("user:1:search-global")
        return time.perf_counter() - started

    assert asyncio.run(run()) >= 0.04


def test_fast_buy_payload_contract_requires_current_price():
    from app.purchase import autobuy

    assert autobuy._extract_item_price({"price": 12.34}) == 12.34
    assert autobuy._extract_item_price({"amount": 12.34}) == 12.34
    assert autobuy._extract_item_price({}) is None


def test_purchase_idempotency_keys_can_be_scoped_per_user():
    from purchase.idempotency import PurchaseIdempotency

    async def run():
        guard = PurchaseIdempotency()
        assert await guard.claim("user::100::id::42")
        assert await guard.claim("user::200::id::42")
        assert not await guard.claim("user::100::id::42")
        await guard.clear()

    asyncio.run(run())
