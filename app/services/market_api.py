from __future__ import annotations

import asyncio
import json
import random
import time
import aiohttp
from urllib.parse import urlsplit

from app.config.settings import (
    BALANCE_CACHE_TTL, BUY_MIN_REQUEST_INTERVAL, FETCH_TIMEOUT,
    LZT_API_KEY, MAX_CONCURRENT_REQUESTS, OTHER_MIN_REQUEST_INTERVAL,
    RETRY_BASE_DELAY, RETRY_MAX, SEARCH_MIN_REQUEST_INTERVAL,
)
from market.rate_limit import AdaptiveRateLimiter

semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
adaptive_rate_limiter = AdaptiveRateLimiter(safety_ms=5)
_global_session: aiohttp.ClientSession | None = None


class RequestRateLimiter:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._next_allowed_at: dict[str, float] = {}

    async def wait(self, bucket: str, min_interval: float):
        if min_interval <= 0:
            return

        while True:
            async with self._lock:
                now = time.monotonic()
                allowed_at = self._next_allowed_at.get(bucket, 0.0)
                wait_for = allowed_at - now
                if wait_for <= 0:
                    self._next_allowed_at[bucket] = now + min_interval
                    return
            await asyncio.sleep(min(wait_for, min_interval))


request_rate_limiter = RequestRateLimiter()


def _is_search_endpoint(url: str) -> bool:
    try:
        path = (urlsplit(url).path or "").strip().lower()
    except Exception:
        return False

    if path.startswith("/category/"):
        return True
    if path in ("/steam", "/fortnite", "/valorant", "/mihoyo", "/epicgames"):
        return True
    return False


def _is_buy_endpoint(url: str) -> bool:
    try:
        path = (urlsplit(url).path or "").strip().lower()
    except Exception:
        return False
    return any(marker in path for marker in ("/buy", "buy/", "/purchase", "purchase/", "confirm-buy", "fast-buy"))


def _api_limit_bucket(method: str, url: str) -> tuple[str, float]:
    if method.upper() == "POST" and _is_buy_endpoint(url):
        return "buy-global", BUY_MIN_REQUEST_INTERVAL
    if method.upper() == "GET" and _is_search_endpoint(url):
        return "search-global", SEARCH_MIN_REQUEST_INTERVAL
    return "other-global", OTHER_MIN_REQUEST_INTERVAL


def _default_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; ParsingBot/1.0; +https://api.lzt.market/)",
        "Referer": "https://zelenka.guru/",
    }
    if LZT_API_KEY:
        headers["Authorization"] = f"Bearer {LZT_API_KEY}"
    return headers


async def get_session():
    global _global_session
    if _global_session is None or _global_session.closed:
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT, connect=3, sock_connect=3, sock_read=FETCH_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=256, limit_per_host=128, ttl_dns_cache=300, enable_cleanup_closed=True)
        _global_session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    return _global_session


async def close_session():
    global _global_session
    if _global_session:
        await _global_session.close()
        _global_session = None


async def fetch_items_raw(url: str, request_timeout: float | None = None):
    bucket, min_interval = _api_limit_bucket("GET", url)
    await request_rate_limiter.wait(bucket, min_interval)
    # Server-header limiter is dormant until the server reports exhaustion; it
    # never adds a fixed delay to the normal discovery hot path.
    await adaptive_rate_limiter.before_request(bucket)
    headers = _default_api_headers()
    timeout_value = max(0.2, float(request_timeout if request_timeout is not None else FETCH_TIMEOUT))
    try:
        session = await get_session()
        async with session.get(url, headers=headers, timeout=timeout_value) as resp:
            await adaptive_rate_limiter.observe(bucket, resp.headers)
            text = await resp.text()

            if resp.status in (400, 401, 403, 404):
                return None, f"HTTP {resp.status}: {text[:300]}", resp.status

            try:
                data = json.loads(text)
            except Exception:
                return None, f"❌ API вернул не JSON:\n{text[:300]}", resp.status

            items = data.get("items")
            if not isinstance(items, list):
                return None, "⚠ API не вернул список items", resp.status

            return items, None, resp.status

    except asyncio.TimeoutError:
        return None, "❌ Таймаут запроса", 0
    except aiohttp.ClientError as e:
        return None, f"❌ Ошибка сети: {e}", 0
    except Exception as e:
        return None, f"❌ Ошибка: {e}", 0


async def fetch_with_retry(url: str, max_retries: int = RETRY_MAX, request_timeout: float | None = None):
    attempt = 0
    retries = max(0, int(max_retries))
    attempts = retries + 1
    delay = RETRY_BASE_DELAY

    while attempt < attempts:
        attempt += 1
        try:
            async with semaphore:
                items, err, status = await fetch_items_raw(url, request_timeout=request_timeout)
        except Exception as e:
            items, err, status = None, f"❌ Ошибка: {e}", 0

        if err is None:
            return items, None

        if status in (400, 401, 403, 404):
            return [], err

        if attempt >= attempts:
            return [], err

        jitter = random.uniform(0, delay * 0.2)
        await asyncio.sleep(delay + jitter)
        delay *= 2

    return [], "❌ Не удалось получить ответ"




def _format_money(v) -> str:
    try:
        return f"{float(v):,.2f}".replace(",", " ").replace(".00", "")
    except Exception:
        try:
            return f"{int(v):,}".replace(",", " ")
        except Exception:
            return str(v)


def _extract_account_buy_balance_text(data) -> str | None:
    candidates = []

    def walk(obj):
        if isinstance(obj, dict):
            title = str(
                obj.get("title")
                or obj.get("name")
                or obj.get("label")
                or obj.get("description")
                or ""
            ).strip()
            oid = obj.get("id")
            amount = obj.get("amount")
            balance = obj.get("balance")
            value = amount if amount is not None else balance
            if title:
                candidates.append((title, oid, value))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(data)

    for title, oid, value in candidates:
        low = title.lower()
        if "баланс для покупки аккаунтов" in low or "buy account" in low or "purchase account" in low:
            parts = [title]
            if oid is not None:
                parts.append(f"ID {oid}")
            if value is not None:
                parts.append(f"{_format_money(value)} ₽")
            return " • ".join(parts)

    for title, oid, value in candidates:
        if oid == LZT_BALANCE_ID:
            parts = [title]
            if oid is not None:
                parts.append(f"ID {oid}")
            if value is not None:
                parts.append(f"{_format_money(value)} ₽")
            return " • ".join(parts)

    return None


async def get_account_buy_balance_text(force: bool = False) -> str:
    cache = user_balance_cache[0]
    now = time.time()
    if not force and cache["text"] != "—" and now - cache["ts"] < BALANCE_CACHE_TTL:
        return cache["text"]

    if not LZT_API_KEY:
        return "—"

    headers = _default_api_headers()
    urls = [
        "https://prod-api.lzt.market/balance/exchange",
        "https://api.lzt.market/balance/exchange",
    ]

    session = await get_session()
    for url in urls:
        try:
            async with session.get(url, headers=headers, timeout=FETCH_TIMEOUT) as resp:
                text = await resp.text()
                if resp.status != 200:
                    continue
                try:
                    data = json.loads(text)
                except Exception:
                    continue
                parsed = _extract_account_buy_balance_text(data)
                if parsed:
                    user_balance_cache[0] = {"text": parsed, "ts": now}
                    return parsed
        except Exception:
            continue

    return cache["text"] if cache["text"] != "—" else "—"

__all__ = [name for name in globals() if not name.startswith("__")]
