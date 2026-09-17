import asyncio
import time

from domain.decision import DecisionEngine
from filters.engine import FilterEngine, FilterSpec
from market.discovery import iter_sources_split
from market.normalize import normalize_market_url
from market.pipeline import DiscoveryPipeline
from market.rate_limit import AdaptiveRateLimiter
from purchase.idempotency import PurchaseIdempotency


def test_filter_and_decision():
    engine = DecisionEngine(
        FilterEngine(FilterSpec(include_title=("genshin",), price_max=100))
    )
    assert engine.decide({"title": "Genshin account", "price": 50}).accepted
    assert not engine.decide({"title": "Steam account", "price": 50}).accepted
    assert not engine.decide({"title": "Genshin account", "price": 150}).accepted


def test_normalize_aliases():
    got = normalize_market_url(
        "https://api.lzt.market/mihoyo?genshinlevelmin=10&orderby=pdate_to_down"
    )
    assert "genshin_level_min=10" in got
    assert "order_by=pdate_to_down" in got


def test_idempotency_one_winner():
    async def run():
        guard = PurchaseIdempotency()
        wins = await asyncio.gather(*(guard.claim("id::1") for _ in range(8)))
        await guard.release("id::1")
        return sum(wins)

    assert asyncio.run(run()) == 1


def test_rate_limiter_no_wait_with_remaining_quota():
    async def run():
        limiter = AdaptiveRateLimiter()
        await limiter.observe(
            "search",
            {
                "X-RateLimit-Remaining": "10",
                "X-RateLimit-Reset": str(time.time() + 10),
            },
        )
        started = time.perf_counter()
        await limiter.before_request("search")
        return time.perf_counter() - started

    assert asyncio.run(run()) < 0.05


def test_discovery_autobuy_first_wave():
    async def run():
        started = []
        release = asyncio.Event()

        async def fetch(source):
            started.append(source["name"])
            await release.wait()
            return source, [{"id": 1}], None

        iterator = iter_sources_split(
            [
                {"name": "plain", "autobuy": False},
                {"name": "buy1", "autobuy": True},
                {"name": "buy2", "autobuy": True},
            ],
            fetch,
            include_non_autobuy=False,
        )
        task = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        first_wave = set(started)
        release.set()
        await task
        return first_wave

    assert asyncio.run(run()) == {"buy1", "buy2"}


def test_pipeline_queues_before_marking_seen():
    async def run():
        marked = []
        queued = []

        async def fetch_sources(_user_id, *, include_non_autobuy):
            assert include_non_autobuy is False
            yield {"name": "buy", "autobuy": True}, [{"id": 42, "price": 10}], None

        async def mark_seen(key):
            marked.append(key)

        async def enqueue(source, item, found_perf):
            queued.append((source["name"], item["id"], found_perf > 0))

        pipeline = DiscoveryPipeline(
            fetch_sources=fetch_sources,
            make_key=lambda item: f"id::{item['id']}",
            is_seen=lambda _key: False,
            is_attempted=lambda _key: False,
            mark_seen=mark_seen,
            enqueue_autobuy=enqueue,
        )
        accepted, stats, errors = await pipeline.run(1, include_non_autobuy=False)
        return accepted, stats, errors, queued, marked

    accepted, stats, errors, queued, marked = asyncio.run(run())
    assert len(accepted) == 1
    assert stats.queued == 1
    assert not errors
    assert queued[0][:2] == ("buy", 42)
    assert marked == ["id::42"]


def test_pipeline_does_not_mark_seen_when_queue_handoff_fails():
    async def run():
        marked = []

        async def fetch_sources(_user_id, *, include_non_autobuy):
            yield {"name": "buy", "autobuy": True}, [{"id": 99}], None

        async def enqueue(_source, _item, _found_perf):
            raise RuntimeError("queue unavailable")

        pipeline = DiscoveryPipeline(
            fetch_sources=fetch_sources,
            make_key=lambda item: f"id::{item['id']}",
            is_seen=lambda _key: False,
            is_attempted=lambda _key: False,
            mark_seen=lambda key: marked.append(key),
            enqueue_autobuy=enqueue,
        )
        try:
            await pipeline.run(1, include_non_autobuy=False)
        except RuntimeError:
            pass
        return marked

    assert asyncio.run(run()) == []
