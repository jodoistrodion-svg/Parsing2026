from __future__ import annotations

import asyncio
import json
import random
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import aiohttp

from app.config.settings import (
    BALANCE_CACHE_TTL,
    BUY_MIN_REQUEST_INTERVAL,
    FETCH_TIMEOUT,
    LZT_API_KEY,
    LZT_BALANCE_ID,
    LZT_BASE_URL,
    MAX_CONCURRENT_REQUESTS,
    OTHER_MIN_REQUEST_INTERVAL,
    RETRY_BASE_DELAY,
    RETRY_MAX,
    RETRY_MAX_DELAY,
    SEARCH_MIN_REQUEST_INTERVAL,
)
from market.rate_limit import AdaptiveRateLimiter
from app.services.credentials import get_lzt_token
from metrics.events import METRICS

semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
adaptive_rate_limiter = AdaptiveRateLimiter(safety_ms=5)
_global_session: aiohttp.ClientSession | None = None
_balance_cache: dict[int | None, dict[str, object]] = {}


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
        "User-Agent": "Mozilla/5.0 (compatible; Parsing2026/3.x; +https://api.lzt.market/)",
        "Referer": "https://zelenka.guru/",
    }
    if LZT_API_KEY:
        headers["Authorization"] = f"Bearer {LZT_API_KEY}"
    return headers




async def _api_headers_for_user(user_id: int | None) -> dict[str, str]:
    if user_id is None:
        return _default_api_headers()
    token = await get_lzt_token(int(user_id))
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Parsing2026/3.x; +https://api.lzt.market/)",
        "Referer": "https://zelenka.guru/",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get_session():
    global _global_session
    if _global_session is None or _global_session.closed:
        timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT, connect=3, sock_connect=3, sock_read=FETCH_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=256, limit_per_host=128, ttl_dns_cache=300, enable_cleanup_closed=True)
        _global_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            trust_env=True,
        )
    return _global_session


async def close_session():
    global _global_session
    if _global_session:
        await _global_session.close()
        _global_session = None


def _retry_after_seconds(headers) -> float | None:
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(raw)
            return max(0.0, dt.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


async def fetch_items_raw(url: str, request_timeout: float | None = None, user_id: int | None = None):
    bucket, min_interval = _api_limit_bucket("GET", url)
    limiter_bucket = f"user:{user_id}:{bucket}" if user_id is not None else bucket
    await request_rate_limiter.wait(limiter_bucket, min_interval)
    await adaptive_rate_limiter.before_request(limiter_bucket)

    headers = await _api_headers_for_user(user_id)
    if user_id is not None and "Authorization" not in headers:
        return None, "LZT API не подключён для этого пользователя", 0
    timeout_value = max(0.2, float(request_timeout if request_timeout is not None else FETCH_TIMEOUT))

    try:
        session = await get_session()
        started = time.perf_counter()
        async with session.get(url, headers=headers, timeout=timeout_value) as resp:
            elapsed = int((time.perf_counter() - started) * 1000)
            await adaptive_rate_limiter.observe(limiter_bucket, resp.headers)
            METRICS.inc("market_requests_total", labels={"method": "GET", "bucket": bucket, "status": resp.status // 100})
            METRICS.observe("market_request_latency_ms", elapsed, labels={"bucket": bucket})
            body = await resp.text()

            if resp.status == 429:
                retry_after = _retry_after_seconds(resp.headers)
                if retry_after is not None:
                    await adaptive_rate_limiter.note_retry_after(limiter_bucket, retry_after)
                return None, f"HTTP 429: {body[:300]}", resp.status

            if resp.status in (400, 401, 403, 404):
                return None, f"HTTP {resp.status}: {body[:300]}", resp.status

            if 500 <= resp.status <= 599 or resp.status in (408, 425):
                return None, f"HTTP {resp.status}: {body[:300]}", resp.status

            try:
                data = json.loads(body)
            except Exception:
                return None, f"API returned non-JSON: {body[:300]}", resp.status

            if not isinstance(data, dict):
                return None, "API returned a non-object JSON response", resp.status

            items = data.get("items")
            if not isinstance(items, list):
                return None, "API did not return an items list", resp.status

            return items, None, resp.status
    except asyncio.TimeoutError:
        METRICS.inc("market_request_errors_total", labels={"kind": "timeout"})
        return None, "request timeout", 0
    except aiohttp.ClientError as exc:
        METRICS.inc("market_request_errors_total", labels={"kind": "client"})
        return None, f"network error: {exc}", 0
    except Exception as exc:
        METRICS.inc("market_request_errors_total", labels={"kind": "unexpected"})
        return None, f"request error: {exc}", 0


async def fetch_with_retry(
    url: str,
    max_retries: int = RETRY_MAX,
    request_timeout: float | None = None,
    user_id: int | None = None,
):
    retries = max(0, int(max_retries))
    delay = max(0.0, RETRY_BASE_DELAY)

    for attempt in range(retries + 1):
        async with semaphore:
            items, err, status = await fetch_items_raw(
                url,
                request_timeout=request_timeout,
                user_id=user_id,
            )

        if err is None:
            return items, None

        retryable = status == 429 or status in (408, 425) or 500 <= status <= 599 or status == 0
        if not retryable or attempt >= retries:
            METRICS.inc(
                "market_failures_total",
                labels={"status": str(status or "network")},
            )
            return [], err

        backoff = min(RETRY_MAX_DELAY, max(0.0, delay))
        jitter = random.uniform(0.0, min(0.05, backoff * 0.2))
        await asyncio.sleep(backoff + jitter)
        delay = min(RETRY_MAX_DELAY, max(delay * 2.0, RETRY_BASE_DELAY))

    return [], "request retry budget exhausted"


def _format_money(v) -> str:
    try:
        return f"{float(v):,.2f}".replace(",", " ").replace(".00", "")
    except Exception:
        try:
            return f"{int(v):,}".replace(",", " ")
        except Exception:
            return str(v)


def invalidate_balance_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _balance_cache.clear()
        return
    _balance_cache.pop(int(user_id), None)


def _extract_account_buy_balance_text(data) -> str | None:
    candidates = []

    def walk(obj):
        if isinstance(obj, dict):
            title = str(obj.get("title") or obj.get("name") or obj.get("label") or obj.get("description") or "").strip()
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


async def get_account_buy_balance_text(user_id: int | None = None, force: bool = False) -> str:
    key = int(user_id) if user_id is not None else None
    cache = _balance_cache.setdefault(key, {"text": "—", "ts": 0.0})
    now = time.time()
    if not force and cache["text"] != "—" and now - float(cache["ts"]) < BALANCE_CACHE_TTL:
        return str(cache["text"])

    headers = await _api_headers_for_user(user_id)
    if user_id is not None and "Authorization" not in headers:
        return "🔴 LZT не подключён"
    if user_id is None and "Authorization" not in headers:
        return "—"

    url = f"{LZT_BASE_URL}/balance/exchange"
    limiter_bucket = f"user:{user_id}:other-global" if user_id is not None else "other-global"
    await request_rate_limiter.wait(limiter_bucket, OTHER_MIN_REQUEST_INTERVAL)
    await adaptive_rate_limiter.before_request(limiter_bucket)
    session = await get_session()
    try:
        async with session.get(url, headers=headers, timeout=FETCH_TIMEOUT) as resp:
            await adaptive_rate_limiter.observe(limiter_bucket, resp.headers)
            body = await resp.text()
            if resp.status == 429:
                retry_after = _retry_after_seconds(resp.headers)
                if retry_after is not None:
                    await adaptive_rate_limiter.note_retry_after(limiter_bucket, retry_after)
                return str(cache["text"]) if cache["text"] != "—" else "🔴 LZT временно ограничил запросы"
            if resp.status != 200:
                return str(cache["text"]) if cache["text"] != "—" else "—"
            try:
                data = json.loads(body)
            except Exception:
                return str(cache["text"]) if cache["text"] != "—" else "—"
            parsed = _extract_account_buy_balance_text(data)
            if parsed:
                cache["text"] = parsed
                cache["ts"] = now
                return parsed
    except (asyncio.TimeoutError, aiohttp.ClientError):
        pass
    return str(cache["text"]) if cache["text"] != "—" else "—"


async def verify_lzt_token(token: str) -> tuple[bool, str]:
    token = (token or "").strip()
    if not token or len(token) > 4096:
        return False, "Пустой или некорректный токен."
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Parsing2026/3.x; +https://api.lzt.market/)",
        "Referer": "https://zelenka.guru/",
        "Authorization": f"Bearer {token}",
    }
    session = await get_session()
    url = f"{LZT_BASE_URL}/balance/exchange"
    limiter_bucket = "verify:other-global"
    await request_rate_limiter.wait(limiter_bucket, OTHER_MIN_REQUEST_INTERVAL)
    await adaptive_rate_limiter.before_request(limiter_bucket)
    try:
        async with session.get(url, headers=headers, timeout=max(FETCH_TIMEOUT, 3.0)) as resp:
            await adaptive_rate_limiter.observe(limiter_bucket, resp.headers)
            body = await resp.text()
            if resp.status == 200:
                try:
                    data = json.loads(body)
                except Exception:
                    data = {}
                label = _extract_account_buy_balance_text(data) or "LZT подключён"
                return True, label
            if resp.status in (401, 403):
                return False, "LZT отклонил токен (401/403)."
    except (asyncio.TimeoutError, aiohttp.ClientError):
        pass
    return False, "Не удалось проверить токен через LZT API."



