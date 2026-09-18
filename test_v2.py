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


def test_settings_module_has_safe_closed_default():
    from app.config.settings import ACCESS_MODE, ACCESS_OPEN
    assert ACCESS_MODE == "closed"
    assert ACCESS_OPEN is False


def test_no_application_import_dependencies():
    from pathlib import Path
    root = Path(__file__).resolve().parent
    offenders = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "from app.application import" in text and path.name != "application.py":
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_application_is_thin_composition_root():
    from pathlib import Path
    text = Path("app/application.py").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 50
    assert "app.runtime.core" in text
    assert "app.purchase.autobuy" in text
    assert "app import handlers" in text


def test_all_python_files_compile():
    from pathlib import Path
    root = Path(__file__).resolve().parent
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_queue_shutdown_cancels_workers():
    from buyer.queue import UserAutobuyQueueManager
    async def run():
        manager = UserAutobuyQueueManager(maxsize=8, workers_per_user=2)
        started = asyncio.Event()
        async def handler(_uid, _payload):
            started.set()
            await asyncio.Event().wait()
        await manager.enqueue(1, "x", handler)
        await asyncio.wait_for(started.wait(), timeout=1)
        assert len(manager._workers.get(1, [])) == 2
        await manager.shutdown()
        return manager._workers, manager._queues
    workers, queues = asyncio.run(run())
    assert workers == {}
    assert queues == {}


def test_discovery_cancellation_cleans_pending_tasks():
    from market.discovery import _run_bounded
    async def run():
        cancelled = 0
        async def fetch(source):
            nonlocal cancelled
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled += 1
                raise
        async def consume():
            async for _ in _run_bounded([{"id": i} for i in range(20)], fetch, limit=4):
                pass
        task = asyncio.create_task(consume())
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return cancelled
    assert asyncio.run(run()) == 4


def test_hunter_runtime_cleanup_is_idempotent():
    from app.purchase import autobuy
    async def run():
        user_id = 424242
        autobuy.user_buy_inflight[user_id].update({"id::1", "id::2"})
        autobuy.user_notify_workers[user_id] = asyncio.current_task()
        autobuy.user_notify_queues[user_id] = asyncio.Queue()
        autobuy.cleanup_user_hunter_runtime(user_id)
        return not autobuy.user_buy_inflight[user_id], user_id in autobuy.user_notify_workers
    cleared, worker_kept = asyncio.run(run())
    assert cleared is True
    assert worker_kept is True


def test_autobuy_total_window_is_monotonic_and_bounded():
    from app.purchase import autobuy
    if autobuy.AUTOBUY_TOTAL_RETRY_WINDOW_SEC <= 0:
        return
    start = time.perf_counter()
    remaining = autobuy._remaining_autobuy_window_sec(start)
    assert 0 < remaining <= autobuy.AUTOBUY_TOTAL_RETRY_WINDOW_SEC


def test_runtime_dependency_versions_are_aligned():
    from pathlib import Path
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "aiogram==3.31.0" in requirements
    assert Path("runtime.txt").read_text(encoding="utf-8").strip() == "python-3.12.2"
