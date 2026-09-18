from __future__ import annotations

import asyncio
import html
import json
import random
import re
import time
from urllib.parse import urlsplit

from app.config.settings import (
    AUTOBUY_BURST_FIRST_WAVE, AUTOBUY_MAX_DURATION_SEC, AUTOBUY_MAX_HTTP_ATTEMPTS,
    AUTOBUY_PARALLEL_HTTP, AUTOBUY_QUEUE_RETRY_MAX_DELAY, AUTOBUY_QUEUE_RETRY_MIN_DELAY,
    AUTOBUY_RETRY_ATTEMPTS, AUTOBUY_RETRY_MAX_DELAY, AUTOBUY_RETRY_MIN_DELAY,
    AUTOBUY_TOTAL_RETRY_WINDOW_SEC, AUTOBUY_URL_LIMIT, FAST_AUTOBUY_TIMEOUT,
    LZT_API_KEY, LZT_BALANCE_ID, LZT_SECRET_WORD, MAX_ITEMS_PER_SOURCE_SCAN,
    MAX_NEW_ITEMS_PER_CYCLE, NON_AUTOBUY_CYCLE_EVERY,
)
from app.runtime.core import (
    bot, _format_value, _safe_compact, autobuy_endpoint_cache, autobuy_queue_manager,
    buy_semaphore, enqueue_hunter_notification, ensure_notify_worker, get_buy_lock,
    load_user_data, log_autobuy, make_card, make_item_key, reset_no_lots_message,
    send_bot_message, user_api_errors, user_buy_attempted, user_buy_inflight, purchase_idempotency,
    user_hunter_interval, user_hunter_mode, user_hunter_tasks, user_notify_queues,
    user_notify_workers, user_search_active, user_seen_items, iter_sources_results_split,
)
from app.services.market_api import _api_limit_bucket, _default_api_headers, get_session, request_rate_limiter
from app.storage.sqlite import db_mark_buy_attempted, db_mark_seen_batch
from bot.autobuy_strategy import build_buy_urls, prioritize_buy_urls
from domain.decision import DecisionEngine
from market.pipeline import DiscoveryPipeline

def _autobuy_buy_urls(source_url: str, item_id: int):
    return build_buy_urls(source_url, item_id)


def _autobuy_cache_key(source_url: str) -> str:
    try:
        p = urlsplit(source_url or "")
        if p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return (source_url or "").strip().lower() or "default"


def _autobuy_prioritized_urls(source_url: str, item_id: int):
    all_urls = _autobuy_buy_urls(source_url, item_id)
    cache_key = _autobuy_cache_key(source_url)
    preferred = autobuy_endpoint_cache.get(cache_key, [])
    pref_item_urls = [tpl.format(id=item_id) for tpl in preferred]
    return prioritize_buy_urls(all_urls, pref_item_urls)


def _remember_autobuy_endpoint(source_url: str, used_url: str):
    cache_key = _autobuy_cache_key(source_url)
    try:
        parts = urlsplit(used_url)
        path = parts.path.lstrip("/")
        item_id_match = re.search(r"/(\d+)(?:/|$)", "/" + path)
        if not item_id_match:
            return
        item_id_str = item_id_match.group(1)
        template_path = path.replace(item_id_str, "{id}", 1)
        template_url = f"{parts.scheme}://{parts.netloc}/{template_path}"
        current = autobuy_endpoint_cache.get(cache_key, [])
        current = [template_url] + [u for u in current if u != template_url]
        autobuy_endpoint_cache[cache_key] = current[:3]
    except Exception:
        pass


def _autobuy_classify_response(status: int, text: str):
    raw = html.unescape(text or "")
    lower = raw.lower()
    data = None
    try:
        data = json.loads(raw)
        joined = json.dumps(data, ensure_ascii=False).lower()
    except Exception:
        joined = lower

    if isinstance(data, dict):
        status_flag = str(data.get("status") or data.get("result") or "").strip().lower()
        success_flag = data.get("success")
        if status_flag in {"error", "failed", "fail"} or success_flag is False:
            return "retry", raw[:220], False

    success_markers = ("success", "ok", "purchased", "purchase complete", "already bought", "уже куп")
    terminal_error_markers = (
        "insufficient", "not enough", "недостаточно", "уже продан", "already sold",
        "already purchased", "already bought", "цена изменилась", "нельзя купить",
        "forbidden", "access denied", "аккаунт продан",
    )
    queue_markers = (
        "в очереди", "queue", "queued", "попробуйте повторить позднее",
    )
    auth_error_markers = (
        "api key", "scope", "token", "unauthorized", "authorization", "bearer",
        "неверный ключ", "доступ запрещен", "доступ запрещён",
    )

    if status in (404, 405):
        return "retry", raw[:220], False
    if status in (200, 201, 202):
        if any(marker in joined for marker in auth_error_markers):
            return "auth", raw[:220], False
        if any(marker in joined for marker in queue_markers):
            return "queue", raw[:220], False
        if any(marker in joined for marker in terminal_error_markers):
            return "terminal", raw[:220], False
        return "success", raw[:220], False
    if status == 401:
        return "auth", raw[:220], False
    if status == 415:
        return "retry", raw[:220], True
    if status == 400 and any(x in joined for x in ("invalid json", "unsupported media", "content-type")):
        return "retry", raw[:220], True

    if any(marker in joined for marker in queue_markers):
        return "queue", raw[:220], False
    if any(marker in joined for marker in success_markers):
        return "success", raw[:220], False
    if any(marker in joined for marker in terminal_error_markers):
        return "terminal", raw[:220], False
    if status == 403:
        if any(marker in joined for marker in auth_error_markers):
            return "auth", raw[:220], False
        return "retry", raw[:220], False
    return "retry", raw[:220], False


def _sanitize_buy_info_for_user(info: str) -> str:
    s = str(info or "")
    s = re.sub(r"https?://\S+", "[api-endpoint]", s)
    return s


def _autobuy_retry_delay(is_queue: bool) -> float:
    if is_queue:
        low = max(0.0, AUTOBUY_QUEUE_RETRY_MIN_DELAY)
        high = max(low, AUTOBUY_QUEUE_RETRY_MAX_DELAY)
    else:
        low = max(0.0, AUTOBUY_RETRY_MIN_DELAY)
        high = max(low, AUTOBUY_RETRY_MAX_DELAY)
    return random.uniform(low, high) if high > 0 else 0.0


def _autobuy_should_retry_by_info(info: str) -> bool:
    low = (info or "").lower()
    if any(x in low for x in (
        "lzt_api_key не задан",
        "ошибка авторизации", "authorization", "unauthorized", "forbidden", "access denied",
        "недостаточно", "insufficient", "already sold", "already bought", "already purchased",
        "уже продан", "нельзя купить", "ручная проверка", "secret",
    )):
        return False
    return True


def _extract_item_price(item: dict):
    for key in ("price", "amount", "sum", "cost"):
        val = item.get(key)
        if val not in (None, "", "—"):
            return val
    return None


def _extract_item_time(item: dict):
    for key in ("published_at", "created_at", "date", "time", "updated_at", "edited_at"):
        val = item.get(key)
        if val not in (None, ""):
            return val
    return None


def _format_item_time_human(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        if isinstance(value, str) and not value.strip().isdigit():
            return value.strip()
        ts = int(float(value))
        if ts > 0:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        pass
    return str(value)


async def _send_buy_result_immediately(chat_id: int, user_id: int, text: str):
    if bot is None:
        enqueue_hunter_notification(user_id, chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        return
    try:
        await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        return
    except Exception as e:
        log_autobuy(f"BUY_NOTIFY_IMMEDIATE_ERR chat_id={chat_id} err='{_safe_compact(str(e),220)}'")
    enqueue_hunter_notification(user_id, chat_id, text, parse_mode="HTML", disable_web_page_preview=True)


def _autobuy_is_terminal_failure(state: str, status: int, info: str) -> bool:
    if state in {"auth", "terminal", "success"}:
        return True
    if status == 401:
        return True
    if status == 403 and state in {"auth", "terminal"}:
        return True
    if status == 400 and (state in {"auth", "terminal"} or "invalid balance" in (info or "").lower()):
        return True
    low = (info or "").lower()
    if any(x in low for x in (
        "already sold", "already purchased", "already bought", "уже продан",
        "нельзя купить", "недостаточно", "insufficient", "аккаунт продан",
    )):
        return True
    return False


def _autobuy_should_mark_attempt(bought: bool, info: str) -> bool:
    if bought:
        return True
    low = (info or "").lower()
    terminal_markers = (
        "недостаточно", "insufficient", "already sold", "already purchased", "already bought",
        "уже продан", "нельзя купить", "ошибка авторизации", "auth",
        "аккаунт продан", "access denied", "forbidden", "unauthorized", "invalid balance",
    )
    return any(x in low for x in terminal_markers)


def _normalize_command_text(text: str) -> str:
    raw = (text or "").strip().lower()
    if not raw:
        return ""

    if raw in {"/start", "start", "старт", "начать"}:
        return "start"
    if raw in {"/menu", "menu", "меню", "главное меню"}:
        return "menu"
    if raw in {"/status", "status", "статус"}:
        return "status"
    if raw in {"/hunter_start", "hunter_start", "start hunter", "старт охотника", "запуск охотника"}:
        return "hunter_start"
    if raw in {"/hunter_stop", "hunter_stop", "stop hunter", "стоп охотника", "остановить охотника"}:
        return "hunter_stop"
    return ""


async def _try_autobuy_once(source: dict, item: dict, found_perf: float | None = None, max_duration_override: float | None = None):
    if not LZT_API_KEY:
        return False, "LZT_API_KEY не задан"

    item_id = item.get("item_id") or item.get("id")
    if not item_id:
        return False, "missing_item_id"

    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return False, f"invalid_item_id={item_id}"

    t0 = time.perf_counter()
    source_name = (source.get("name") or "UNKNOWN").strip()
    source_url = (source.get("url") or "").strip()
    buy_urls = _autobuy_prioritized_urls(source_url, item_id)
    if AUTOBUY_URL_LIMIT > 0:
        buy_urls = buy_urls[:AUTOBUY_URL_LIMIT]

    if not buy_urls:
        return False, "buy_url_not_found"

    payload = {
        "balance_id": LZT_BALANCE_ID,
        "buy_without_validation": 1,
    }
    if LZT_SECRET_WORD:
        payload["secret_answer"] = LZT_SECRET_WORD

    since_found_ms = None
    if found_perf is not None:
        since_found_ms = int((t0 - found_perf) * 1000)

    max_attempts = AUTOBUY_MAX_HTTP_ATTEMPTS if AUTOBUY_MAX_HTTP_ATTEMPTS > 0 else len(buy_urls)
    attempt_urls = buy_urls[:max_attempts]
    parallel_requests = max(1, min(len(attempt_urls), AUTOBUY_PARALLEL_HTTP if AUTOBUY_PARALLEL_HTTP > 0 else len(attempt_urls)))

    log_autobuy(
        f"BUY_START item_id={item_id} src='{_safe_compact(source_name,120)}' "
        f"since_found_ms={since_found_ms} urls={len(attempt_urls)} parallel={parallel_requests} buy_without_validation=1"
    )

    session = await get_session()
    common_headers = _default_api_headers()
    headers_json = {**common_headers, "Content-Type": "application/json"}
    headers_form = {**common_headers, "Content-Type": "application/x-www-form-urlencoded"}

    async def _post_buy(idx: int, buy_url: str):
        post_started = time.perf_counter()
        try:
            bucket, min_interval = _api_limit_bucket("POST", buy_url)

            await request_rate_limiter.wait(bucket, min_interval)
            t4 = time.perf_counter()
            async with session.post(buy_url, headers=headers_json, json=payload, timeout=FAST_AUTOBUY_TIMEOUT) as resp:
                body = await resp.text()
                t5 = time.perf_counter()
                state, info, force_form = _autobuy_classify_response(resp.status, body)
                log_autobuy(
                    f"BUY_DIRECT item_id={item_id} attempt={idx}/{len(attempt_urls)} "
                    f"status={resp.status} state={state} mode=json url={buy_url} post_ms={int((t5-t4)*1000)} total_ms={int((t5-post_started)*1000)} info='{_safe_compact(info,220)}'"
                )

            if force_form:
                # Фолбэк формой запускаем сразу, без дополнительной паузы,
                # чтобы не терять драгоценные миллисекунды на hot-path автобая.
                async with session.post(buy_url, headers=headers_form, data=payload, timeout=FAST_AUTOBUY_TIMEOUT) as resp_form:
                    body_form = await resp_form.text()
                    t5_form = time.perf_counter()
                    state_form, info_form, _ = _autobuy_classify_response(resp_form.status, body_form)
                    log_autobuy(
                        f"BUY_DIRECT item_id={item_id} attempt={idx}/{len(attempt_urls)} "
                        f"status={resp_form.status} state={state_form} mode=form url={buy_url} post_ms={int((t5_form-t4)*1000)} total_ms={int((t5_form-post_started)*1000)} info='{_safe_compact(info_form,220)}'"
                    )
                    return idx, buy_url, resp_form.status, state_form, info_form

            return idx, buy_url, resp.status, state, info
        except asyncio.TimeoutError:
            return idx, buy_url, 0, "timeout", "buy_timeout"
        except Exception as e:
            return idx, buy_url, 0, "error", str(e)

    async with buy_semaphore:
        last_error = "no_attempts"
        pending: set[asyncio.Task] = set()
        next_idx = 0
        burst_wave = max(1, min(parallel_requests, AUTOBUY_BURST_FIRST_WAVE if AUTOBUY_BURST_FIRST_WAVE > 0 else parallel_requests))
        max_duration_sec = AUTOBUY_MAX_DURATION_SEC
        if max_duration_override is not None:
            max_duration_sec = max(0.0, min(max_duration_sec if max_duration_sec > 0 else max_duration_override, max_duration_override))
        deadline = t0 + max_duration_sec if max_duration_sec > 0 else None

        while next_idx < len(attempt_urls) or pending:
            now = time.perf_counter()
            if deadline and now >= deadline:
                break

            target_parallel = burst_wave if next_idx < burst_wave else parallel_requests
            while next_idx < len(attempt_urls) and len(pending) < target_parallel:
                idx = next_idx + 1
                pending.add(asyncio.create_task(_post_buy(idx, attempt_urls[next_idx])))
                next_idx += 1

            if not pending:
                continue

            wait_timeout = None
            if deadline:
                wait_timeout = max(0.001, deadline - time.perf_counter())

            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=wait_timeout)
            if not done:
                break

            for task in done:
                t_idx, t_url, status, state, info = await task

                if state == "success":
                    log_autobuy(f"BUY_T6_SUCCESS item_id={item_id} since_found_ms={int((time.perf_counter()-found_perf)*1000) if found_perf is not None else -1} attempt={t_idx}")
                    _remember_autobuy_endpoint(source_url, t_url)
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return True, f"{t_url} -> {info}"
                if state == "auth":
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return False, f"{t_url} -> HTTP {status}: ошибка авторизации API ({info})"
                if state == "secret":
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return False, f"{t_url} -> требуется ручная проверка/секретный ответ ({info})"
                if state == "terminal":
                    _remember_autobuy_endpoint(source_url, t_url)
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return False, f"{t_url} -> {info}"
                if state == "queue":
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return False, f"{t_url} -> queue: {info}"

                if state in {"timeout", "error"}:
                    last_error = f"{t_url} -> {info}"
                    continue

                last_error = f"{t_url} -> HTTP {status}: {info}"
                if _autobuy_is_terminal_failure(state, status, info):
                    for p in pending:
                        p.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    return False, last_error

        if pending:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        if deadline and time.perf_counter() >= deadline and last_error == "no_attempts":
            return False, "autobuy_deadline_reached"
        return False, last_error


def _remaining_autobuy_window_sec(found_perf: float | None) -> float | None:
    if found_perf is None:
        return None
    if AUTOBUY_TOTAL_RETRY_WINDOW_SEC <= 0:
        return None
    elapsed = time.perf_counter() - found_perf
    return AUTOBUY_TOTAL_RETRY_WINDOW_SEC - elapsed


async def try_autobuy_item(source: dict, item: dict, found_perf: float | None = None):
    item_key = make_item_key(item)
    lock = get_buy_lock(item_key)

    async with lock:
        attempts_limit = AUTOBUY_RETRY_ATTEMPTS if AUTOBUY_RETRY_ATTEMPTS > 0 else None
        last_info = "autobuy_no_attempts"

        i = 0
        while True:
            i += 1
            max_attempt_window = _remaining_autobuy_window_sec(found_perf)
            if max_attempt_window is not None and max_attempt_window <= 0:
                return False, f"attempt={i}/{attempts_limit if attempts_limit is not None else '∞'} | autobuy_total_retry_window_exceeded"

            bought, info = await _try_autobuy_once(source, item, found_perf=found_perf, max_duration_override=max_attempt_window)
            last_info = str(info)
            if bought:
                total = attempts_limit if attempts_limit is not None else "∞"
                return True, f"attempt={i}/{total} | {info}"

            if not _autobuy_should_retry_by_info(last_info):
                total = attempts_limit if attempts_limit is not None else "∞"
                return False, f"attempt={i}/{total} | {info}"

            if attempts_limit is not None and i >= attempts_limit:
                return False, f"attempt={i}/{attempts_limit} | {last_info}"

            is_queue = "queue" in last_info.lower()
            delay = _autobuy_retry_delay(is_queue=is_queue)
            if delay > 0:
                await asyncio.sleep(delay)


async def _run_autobuy_and_notify(user_id: int, chat_id: int, source: dict, item: dict, found_perf: float):
    item_id = item.get("item_id") or item.get("id")
    item_key = make_item_key(item)
    src_name = source.get("name") or "UNKNOWN"
    bought = False
    buy_info = "autobuy_not_started"
    should_mark_attempt = False
    claimed = await purchase_idempotency.claim(item_key)
    if not claimed:
        user_buy_inflight[user_id].discard(item_key)
        return
    try:
        bought, buy_info = await try_autobuy_item(source, item, found_perf=found_perf)
        should_mark_attempt = _autobuy_should_mark_attempt(bought, str(buy_info))
        user_buy_inflight[user_id].discard(item_key)
        if should_mark_attempt and item_key not in user_buy_attempted[user_id]:
            user_buy_attempted[user_id].add(item_key)
            await db_mark_buy_attempted(user_id, item_key)
    except Exception as e:
        user_buy_inflight[user_id].discard(item_key)
        buy_info = f"autobuy_runtime_error: {e}"
        log_autobuy(f"BUY_MARK_ERR user_id={user_id} item_key={item_key} err='{_safe_compact(str(e),220)}'")
    finally:
        await purchase_idempotency.release(item_key)

    dur_ms = int((time.perf_counter() - found_perf) * 1000)
    log_autobuy(f"BUY_T6_RESULT item_id={item_id} since_found_ms={dur_ms} bought={int(bool(bought))}")
    bought_link = item.get("url") or item.get("link") or (f"https://lzt.market/{item_id}" if item_id is not None else "")
    lot_price = _extract_item_price(item)
    lot_time = _format_item_time_human(_extract_item_time(item))
    now_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    result_emoji = "✅" if bought else "❌"
    result_word = "Успех" if bought else "Ошибка"
    buy_result_text = (
        f"🛒 <b>Автобай {result_emoji}</b> [{html.escape(src_name)}]\n"
        f"📌 Статус: <b>{result_word}</b>\n"
        f"🆔 item_id: <code>{html.escape(str(item_id))}</code>\n"
        f"⏱ Время покупки: <b>{html.escape(now_text)}</b>\n"
        f"⚡ Задержка после обнаружения: <b>{dur_ms}ms</b>\n"
        f"💰 Цена: <b>{html.escape(_format_value(lot_price) if lot_price is not None else '—')} ₽</b>\n"
        f"🕒 Время лота: <b>{html.escape(lot_time)}</b>\n"
        f"🔗 Лот: {html.escape(str(bought_link))}\n"
        f"ℹ️ Детали: {html.escape(_sanitize_buy_info_for_user(str(buy_info)))}"
    )

    log_autobuy(
        f"BUY_RESULT user_id={user_id} item_key={item_key} bought={int(bool(bought))} "
        f"persist_attempt={int(bool(should_mark_attempt))} info='{_safe_compact(str(buy_info),240)}'"
    )

    await _send_buy_result_immediately(chat_id, user_id, buy_result_text)


async def _autobuy_queue_handler(user_id: int, payload: tuple[int, dict, dict, float]):
    chat_id, source, item, found_perf = payload
    await _run_autobuy_and_notify(user_id, chat_id, source, item, found_perf)




async def _mark_seen_and_batch(key: str, user_id: int, seen_batch: list[str]):
    user_seen_items[user_id].add(key)
    seen_batch.append(key)

def cleanup_user_hunter_runtime(user_id: int):
    user_buy_inflight[user_id].clear()
    task = user_hunter_tasks.get(user_id)
    if task is asyncio.current_task():
        user_hunter_tasks.pop(user_id, None)
    worker = user_notify_workers.get(user_id)
    if worker is not None and worker.done():
        user_notify_workers.pop(user_id, None)
        user_notify_queues.pop(user_id, None)


async def hunter_loop_for_user(user_id: int, chat_id: int):
    await load_user_data(user_id)
    user_buy_inflight[user_id].clear()
    ensure_notify_worker(user_id)
    no_lots_streak = 0
    cycle_num = 0

    async def fetch_sources(uid: int, *, include_non_autobuy: bool):
        async for result in iter_sources_results_split(uid, include_non_autobuy=include_non_autobuy):
            yield result

    async def mark_seen(key: str):
        user_seen_items[user_id].add(key)

    async def enqueue_autobuy(source: dict, item: dict, found_perf: float):
        key = make_item_key(item)
        if key in user_buy_attempted[user_id] or key in user_buy_inflight[user_id]:
            return
        user_buy_inflight[user_id].add(key)
        try:
            return await autobuy_queue_manager.enqueue(
                user_id, (chat_id, source, item, found_perf), _autobuy_queue_handler
            )
        except Exception:
            user_buy_inflight[user_id].discard(key)
            raise

    while user_search_active[user_id]:
        cycle_num += 1
        include_non_autobuy = NON_AUTOBUY_CYCLE_EVERY <= 1 or (cycle_num % NON_AUTOBUY_CYCLE_EVERY == 0)
        seen_batch: list[str] = []
        new_items_processed = 0
        try:
            pipeline = DiscoveryPipeline(
                fetch_sources=fetch_sources,
                make_key=make_item_key,
                is_seen=lambda key: key in user_seen_items[user_id],
                is_attempted=lambda key: key in user_buy_attempted[user_id] or key in user_buy_inflight[user_id],
                mark_seen=lambda key: _mark_seen_and_batch(key, user_id, seen_batch),
                enqueue_autobuy=enqueue_autobuy,
                decision=DecisionEngine(),
                max_items_per_source=MAX_ITEMS_PER_SOURCE_SCAN,
                max_new_items_per_cycle=MAX_NEW_ITEMS_PER_CYCLE,
            )
            accepted, stats, errors = await pipeline.run(user_id, include_non_autobuy=include_non_autobuy)
            for _name, _url, _err in errors:
                user_api_errors[user_id] += 1

            for entry in accepted:
                if MAX_NEW_ITEMS_PER_CYCLE > 0 and new_items_processed >= MAX_NEW_ITEMS_PER_CYCLE:
                    break
                src_name = entry.source.get("name") or "UNKNOWN"
                try:
                    await send_bot_message(
                        chat_id, make_card(entry.item, src_name),
                        parse_mode="HTML", disable_web_page_preview=True
                    )
                except Exception as e:
                    log_autobuy(f"LOT_NOTIFY_SEND_ERR user_id={user_id} err='{_safe_compact(str(e),240)}'")
                new_items_processed += 1

            if new_items_processed == 0:
                no_lots_streak += 1
            else:
                no_lots_streak = 0
                reset_no_lots_message(user_id)

            if seen_batch:
                await db_mark_seen_batch(user_id, seen_batch)
            await asyncio.sleep(await user_hunter_interval(user_id))

        except asyncio.CancelledError:
            user_hunter_mode[user_id] = "off"
            break
        except Exception as e:
            if seen_batch:
                try:
                    await db_mark_seen_batch(user_id, seen_batch)
                except Exception:
                    pass
            user_api_errors[user_id] += 1
            log_autobuy(f"HUNTER_EXC user_id={user_id} err='{_safe_compact(str(e),400)}'")
            await asyncio.sleep(max(await user_hunter_interval(user_id), 0.01))

    await autobuy_queue_manager.stop_user(user_id)
    cleanup_user_hunter_runtime(user_id)

__all__ = [name for name in globals() if not name.startswith("__")]
