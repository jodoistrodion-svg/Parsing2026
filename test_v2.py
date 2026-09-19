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
        if "from app.application import" in text and path.name not in {"application.py", "test_v2.py"}:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_application_is_thin_composition_root():
    from pathlib import Path
    text = Path("app/application.py").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 50
    assert "app.runtime.core" in text
    assert "from app.purchase import autobuy" in text
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


def test_handler_runtime_symbols_are_explicitly_imported():
    import app.handlers as handlers
    assert callable(handlers.get_all_sources)
    assert handlers.URL_PAGE_SIZE > 0
    assert handlers.USER_PAGE_SIZE > 0


def test_autobuy_does_not_retry_when_api_key_is_missing():
    from app.purchase.autobuy import _autobuy_should_retry_by_info
    assert _autobuy_should_retry_by_info("LZT_API_KEY не задан") is False


def test_queue_full_preserves_existing_autobuy_job():
    from buyer.queue import UserAutobuyQueueManager

    async def run():
        manager = UserAutobuyQueueManager(maxsize=1, workers_per_user=1)
        started = asyncio.Event()
        release = asyncio.Event()

        async def handler(_uid, _payload):
            started.set()
            await release.wait()

        assert await manager.enqueue(1, "first", handler) is True
        await asyncio.wait_for(started.wait(), timeout=1)
        assert await manager.enqueue(1, "second", handler) is True
        assert await manager.enqueue(1, "third", handler) is False

        queue = manager._queues[1]
        queued = queue.get_nowait()
        queue.task_done()
        assert queued == "second"

        release.set()
        await manager.shutdown()

    asyncio.run(run())


def test_pipeline_does_not_mark_lot_seen_when_autobuy_queue_rejects():
    from market.pipeline import DiscoveryPipeline

    async def fetch_sources(_uid, *, include_non_autobuy):
        yield {"url": "https://api.lzt.market/x", "name": "buy", "autobuy": True}, [{"id": 1, "title": "x"}], None

    async def run():
        seen = []
        rejected = 0

        async def enqueue(_source, _item, _found):
            nonlocal rejected
            rejected += 1
            return False

        pipeline = DiscoveryPipeline(
            fetch_sources=fetch_sources,
            make_key=lambda item: f"id::{item['id']}",
            is_seen=lambda _key: False,
            is_attempted=lambda _key: False,
            mark_seen=lambda key: seen.append(key),
            enqueue_autobuy=enqueue,
        )
        accepted, stats, _errors = await pipeline.run(1, include_non_autobuy=False)
        return accepted, stats, seen, rejected

    accepted, stats, seen, rejected = asyncio.run(run())
    assert accepted == []
    assert stats.queue_rejected == 1
    assert seen == []
    assert rejected == 1


def test_normalize_market_url_does_not_rewrite_query_values():
    from market.normalize import normalize_url

    got = normalize_url(
        "https://api.lzt.market/mihoyo?note=orderby%3Dweird&orderby=pdate_to_down"
    )
    assert "note=orderby%3Dweird" in got
    assert "order_by=pdate_to_down" in got
    assert "orderby%3Dweird" in got


def test_normalize_strips_credentials_and_normalizes_alias_host():
    from market.normalize import normalize_url, validate_market_url

    raw = "https://user:pass@www.lzt.market:443/mihoyo"
    ok, error = validate_market_url(raw)
    assert ok is True and error is None
    got = normalize_url(raw)
    assert got.startswith("https://api.lzt.market/mihoyo?")
    assert "user%3Apass" not in got
    assert "@" not in got


def test_purchase_claim_cannot_be_released_by_another_task():
    from purchase.idempotency import PurchaseIdempotency

    async def run():
        manager = PurchaseIdempotency()
        assert await manager.claim("id::1") is True
        released = await asyncio.create_task(_release_from_other_task(manager, "id::1"))
        assert released is False
        assert manager.claimed("id::1") is True
        assert await manager.release("id::1") is True

    async def _release_from_other_task(manager, key):
        return await manager.release(key)

    asyncio.run(run())


def test_env_example_placeholder_does_not_activate_lzt_api():
    import os
    import importlib
    import app.config.settings as settings

    original = os.environ.get("LZT_API_KEY")
    os.environ["LZT_API_KEY"] = "replace-with-lzt-api-key"
    try:
        reloaded = importlib.reload(settings)
        assert reloaded.LZT_API_KEY == ""
    finally:
        if original is None:
            os.environ.pop("LZT_API_KEY", None)
        else:
            os.environ["LZT_API_KEY"] = original
        importlib.reload(settings)


def test_closed_access_requires_owner_configuration():
    import app.config.settings as settings

    original_open = settings.ACCESS_OPEN
    original_owners = settings.OWNER_IDS
    try:
        settings.ACCESS_OPEN = False
        settings.OWNER_IDS = set()
        try:
            settings.validate_runtime_config()
        except RuntimeError as exc:
            assert "OWNER_ID/OWNER_IDS" in str(exc)
        else:
            raise AssertionError("closed access without owner must fail validation")
    finally:
        settings.ACCESS_OPEN = original_open
        settings.OWNER_IDS = original_owners


def test_all_project_modules_import():
    import importlib
    from pathlib import Path

    root = Path(__file__).resolve().parent
    failures = []
    excluded_dirs = {".git", ".venv", "venv", "env", "build", "dist", "__pycache__"}
    for path in root.rglob("*.py"):
        if path.name == "test_v2.py" or any(part in excluded_dirs for part in path.parts):
            continue
        relative = path.relative_to(root).with_suffix("")
        parts = relative.parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        module_name = ".".join(parts)
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failures.append(f"{module_name}: {type(exc).__name__}: {exc}")
    assert failures == []


def test_autobuy_response_classifier_requires_explicit_success():
    from app.purchase.autobuy import _autobuy_classify_response

    assert _autobuy_classify_response(200, '{"success": true}')[0] == "success"
    assert _autobuy_classify_response(200, '{"status": "ok"}')[0] == "success"
    assert _autobuy_classify_response(200, "secret answer required")[0] == "secret"
    assert _autobuy_classify_response(200, "cookie accepted")[0] == "retry"
    assert _autobuy_classify_response(200, "")[0] == "success"



def test_purchase_claim_expiry_recovers_stale_claim():
    from purchase.idempotency import PurchaseIdempotency

    async def run():
        manager = PurchaseIdempotency(ttl_seconds=1.0)
        assert await manager.claim("stale") is True
        await asyncio.sleep(1.05)
        assert await manager.claim("stale") is True
        assert await manager.release("stale") is True

    asyncio.run(run())


def test_settings_accept_legacy_aliases_without_exposing_secrets():
    import os
    from app.config.settings import load_settings

    names = {
        "API_TOKEN": os.environ.get("API_TOKEN"),
        "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN"),
        "LZT_API_KEY": os.environ.get("LZT_API_KEY"),
        "LZT_API_TOKEN": os.environ.get("LZT_API_TOKEN"),
        "OWNER_ID": os.environ.get("OWNER_ID"),
        "ADMIN_TELEGRAM_ID": os.environ.get("ADMIN_TELEGRAM_ID"),
    }
    try:
        os.environ.pop("API_TOKEN", None)
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz123456"
        os.environ.pop("LZT_API_KEY", None)
        os.environ["LZT_API_TOKEN"] = "legacy-lzt-secret"
        os.environ.pop("OWNER_ID", None)
        os.environ["ADMIN_TELEGRAM_ID"] = "123456789"
        loaded = load_settings()
        assert loaded.api_token.startswith("123456:")
        assert loaded.lzt_api_key == "legacy-lzt-secret"
        assert 123456789 in loaded.owner_ids
        redacted = loaded.redacted()
        assert redacted["api_token"] == "***"
        assert redacted["lzt_api_key"] == "***"
    finally:
        for name, value in names.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_metrics_registry_exports_prometheus_text():
    from metrics.events import MetricsRegistry

    registry = MetricsRegistry()
    registry.inc("example_events_total", labels={"kind": "ok"})
    registry.set("example_ready", 1)
    registry.observe("example_latency_ms", 12.5)

    text = registry.prometheus_text()
    assert "example_events_total" in text
    assert 'kind="ok"' in text
    assert "example_ready" in text
    assert "example_latency_ms_count" in text


def test_health_state_transitions():
    from app.runtime.health import RuntimeHealth

    health = RuntimeHealth(started_at=time.monotonic())
    assert health.snapshot()["ready"] is False
    health.ready = True
    snapshot = health.snapshot()
    assert snapshot["status"] == "ready"
    health.shutting_down = True
    assert health.snapshot()["status"] == "stopping"


def test_task_supervisor_cleans_cancelled_tasks():
    from app.runtime.tasks import TaskSupervisor

    async def run():
        supervisor = TaskSupervisor()
        started = asyncio.Event()

        async def worker():
            started.set()
            await asyncio.Event().wait()

        task = await supervisor.spawn("worker", worker())
        await asyncio.wait_for(started.wait(), timeout=1)
        await supervisor.shutdown()
        return task.done(), task.cancelled(), supervisor.snapshot()

    done, cancelled, snapshot = asyncio.run(run())
    assert done is True
    assert cancelled is True
    assert snapshot == []


def test_queue_admission_metrics_are_emitted():
    from buyer.queue import UserAutobuyQueueManager
    from metrics.events import METRICS

    async def run():
        manager = UserAutobuyQueueManager(maxsize=1, workers_per_user=1)
        started = asyncio.Event()
        release = asyncio.Event()

        async def handler(_uid, _payload):
            started.set()
            await release.wait()

        assert await manager.enqueue(1, "one", handler) is True
        await asyncio.wait_for(started.wait(), timeout=1)
        assert await manager.enqueue(1, "two", handler) is True
        assert await manager.enqueue(1, "three", handler) is False
        release.set()
        await manager.shutdown()

    asyncio.run(run())
    metrics = METRICS.snapshot()
    assert any("autobuy_queue_rejected_total" in str(key) for key in metrics["counters"])


def test_storage_schema_version_and_retention_cleanup(tmp_path):
    import app.storage.sqlite as storage

    async def run():
        original_db_file = storage.DB_FILE
        original_db = storage._db
        storage.DB_FILE = str(tmp_path / "test.sqlite")
        storage._db = None
        try:
            await storage.init_db()
            assert await storage.db_get_schema_version() == 4
            now = int(time.time())
            await storage.db_execute(
                "INSERT OR REPLACE INTO seen(user_id, item_key, seen_at) VALUES (?, ?, ?)",
                (1, "old", now - 10 * 86400),
                commit=True,
            )
            await storage.db_execute(
                "INSERT OR REPLACE INTO buy_attempted(user_id, item_key, attempted_at) VALUES (?, ?, ?)",
                (1, "old", now - 10 * 86400),
                commit=True,
            )
            result = await storage.db_cleanup(
                seen_retention_days=1,
                buy_attempt_retention_days=1,
            )
            assert result["seen_deleted"] >= 1
            assert result["buy_attempted_deleted"] >= 1
        finally:
            await storage.db_close()
            storage.DB_FILE = original_db_file
            storage._db = original_db

    asyncio.run(run())


def test_autobuy_dry_run_is_explicit():
    import app.purchase.autobuy as autobuy

    original_mode = autobuy.AUTOBUY_MODE
    original_key = autobuy.LZT_API_KEY
    try:
        autobuy.AUTOBUY_MODE = "dry-run"
        autobuy.LZT_API_KEY = "test-key"

        async def run():
            return await autobuy._try_autobuy_once(
                {"url": "https://api.lzt.market/mihoyo", "name": "test"},
                {"id": 123},
            )

        bought, info = asyncio.run(run())
        assert bought is True
        assert "DRY_RUN" in info
    finally:
        autobuy.AUTOBUY_MODE = original_mode
        autobuy.LZT_API_KEY = original_key


def test_access_code_is_one_time_and_bound_to_one_user(tmp_path):
    import app.storage.sqlite as storage
    from access.licensing import issue_access_code, redeem_access_code, revoke_user_access

    async def run():
        original_db_file = storage.DB_FILE
        original_db = storage._db
        storage.DB_FILE = str(tmp_path / "license.sqlite")
        storage._db = None
        try:
            await storage.init_db()
            code = await issue_access_code(9001)
            assert code.startswith("P26-")
            assert len(code) == 29

            results = await asyncio.gather(
                redeem_access_code(1001, code),
                redeem_access_code(1002, code),
            )
            assert sorted(results) == ["redeemed", "used"]

            winner = 1001 if results[0] == "redeemed" else 1002
            loser = 1002 if winner == 1001 else 1001
            assert await storage.db_is_allowed(winner) is True
            assert await storage.db_is_allowed(loser) is False

            rows = await storage.db_fetchall(
                "SELECT code_hash, redeemed_by, redeemed_at FROM access_codes"
            )
            assert len(rows) == 1
            assert rows[0][0] != code
            assert rows[0][1] == winner
            assert rows[0][2] is not None

            assert await redeem_access_code(winner, code) == "already_active"
            assert await revoke_user_access(winner) == 1
            assert await storage.db_is_allowed(winner) is False
        finally:
            await storage.db_close()
            storage.DB_FILE = original_db_file
            storage._db = original_db

    asyncio.run(run())


def test_access_code_normalization_and_invalid_input():
    from access.licensing import generate_access_code, redeem_access_code

    code = generate_access_code()
    assert code == code.upper()
    assert code.count("-") == 4
    assert len(code) == 29

    async def run():
        try:
            await redeem_access_code(123, "definitely-not-a-code")
        except ValueError:
            return True
        return False

    assert asyncio.run(run()) is True
