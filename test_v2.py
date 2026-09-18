import asyncio
import time
from domain.decision import DecisionEngine
from filters.engine import FilterEngine, FilterSpec
from market.discovery import iter_sources_split
from market.normalize import normalize_market_url
from market.rate_limit import AdaptiveRateLimiter
from purchase.idempotency import PurchaseIdempotency

def test_filter_and_decision():
    engine=DecisionEngine(FilterEngine(FilterSpec(include_title=("genshin",),price_max=100)))
    assert engine.decide({"title":"Genshin account","price":50}).accepted
    assert not engine.decide({"title":"Steam account","price":50}).accepted
    assert not engine.decide({"title":"Genshin account","price":150}).accepted

def test_normalize_aliases():
    got=normalize_market_url("https://api.lzt.market/mihoyo?genshinlevelmin=10&orderby=pdate_to_down")
    assert "genshin_level_min=10" in got and "order_by=pdate_to_down" in got

def test_idempotency_one_winner():
    async def run():
        g=PurchaseIdempotency()
        wins=await asyncio.gather(*(g.claim("id::1") for _ in range(8)))
        await g.release("id::1")
        return sum(wins)
    assert asyncio.run(run())==1

def test_rate_limiter_no_wait_with_remaining_quota():
    async def run():
        g=AdaptiveRateLimiter()
        await g.observe("search",{"X-RateLimit-Remaining":"10","X-RateLimit-Reset":str(time.time()+10)})
        t=time.perf_counter(); await g.before_request("search"); return time.perf_counter()-t
    assert asyncio.run(run())<0.05

def test_discovery_autobuy_first_wave():
    async def run():
        started=[]; release=asyncio.Event()
        async def fetch(s):
            started.append(s["name"]); await release.wait(); return s,[{"id":1}],None
        it=iter_sources_split([{"name":"plain","autobuy":False},{"name":"buy1","autobuy":True},{"name":"buy2","autobuy":True}],fetch,include_non_autobuy=False)
        task=asyncio.create_task(it.__anext__()); await asyncio.sleep(0); await asyncio.sleep(0); first=set(started); release.set(); await task
        return first
    assert asyncio.run(run())=={"buy1","buy2"}


def test_item_sort_key_accepts_iso8601():
    from market.pipeline import _item_sort_key
    old = _item_sort_key({"id": 1, "published_at": "2026-09-18T10:00:00Z"})
    new = _item_sort_key({"id": 2, "published_at": "2026-09-18T10:01:00+00:00"})
    assert old[0] > 0
    assert new[0] > old[0]


def test_retry_count_is_retries_plus_initial_attempt():
    import app.services.market_api as market_api
    async def run():
        calls=[]
        original=market_api.fetch_items_raw
        async def fake(*args, **kwargs):
            calls.append(1)
            return None, "temporary", 0
        market_api.fetch_items_raw=fake
        try:
            await market_api.fetch_with_retry("https://api.lzt.market/mihoyo", max_retries=2)
        finally:
            market_api.fetch_items_raw=original
        return len(calls)
    assert asyncio.run(run()) == 3


def test_main_entrypoint_imports():
    import main
    assert callable(main.main)


def test_bootstrap_imports():
    from app.bootstrap import main
    assert callable(main)


def test_discovery_bounded_in_flight():
    import market.discovery as discovery
    assert discovery.DISCOVERY_MAX_IN_FLIGHT == 64
