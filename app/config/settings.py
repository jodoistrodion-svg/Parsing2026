from __future__ import annotations

import os
import re
from dotenv import load_dotenv

load_dotenv()


def _normalize_telegram_token(raw: str | None) -> str:
    token = (raw or "").strip().strip('"').strip("'")
    if token.lower().startswith("bot") and re.match(r"^bot\d{6,12}:", token, flags=re.IGNORECASE):
        token = token[3:]
    return token


def _cfg(name: str, fallback: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else fallback.strip()


def _int(name: str, default: int, minimum: int | None = None) -> int:
    raw = _cfg(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _float(name: str, default: float, minimum: float | None = None) -> float:
    raw = _cfg(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


API_TOKEN = _normalize_telegram_token(
    _cfg("API_TOKEN", _cfg("TELEGRAM_BOT_TOKEN", _cfg("BOT_TOKEN")))
)
LZT_API_KEY = _cfg("LZT_API_KEY", _cfg("LZT_TOKEN", _cfg("LOLZ_API_KEY")))
LZT_BALANCE_ID = _int("LZT_BALANCE_ID", 20212, minimum=1)

OWNER_ID = _int("OWNER_ID", 0, minimum=0)
_raw_owner_ids = _cfg("OWNER_IDS")
if _raw_owner_ids:
    OWNER_IDS = {
        int(x.strip())
        for x in _raw_owner_ids.split(",")
        if x.strip().lstrip("-").isdigit()
    }
else:
    OWNER_IDS = {OWNER_ID} if OWNER_ID else set()

ACCESS_MODE = (_cfg("ACCESS_MODE", "closed") or "closed").strip().lower()
ACCESS_OPEN = ACCESS_MODE in {"open", "all", "public", "0"}

HUNTER_INTERVAL_BASE = _float("HUNTER_INTERVAL_BASE", 0.02, minimum=0.0)
FETCH_TIMEOUT = _float("FETCH_TIMEOUT", 1.20, minimum=0.2)
BUY_TIMEOUT = _float("BUY_TIMEOUT", 0.32, minimum=0.0)
RETRY_MAX = _int("RETRY_MAX", 1, minimum=0)
RETRY_BASE_DELAY = _float("RETRY_BASE_DELAY", 0.01, minimum=0.0)

SHORT_CARD_MAX = 3200
ERROR_REPORT_INTERVAL = 3600
MAX_URLS_PER_USER_DEFAULT = 50
MAX_URLS_PER_USER_LIMITED = 3
MAX_CONCURRENT_REQUESTS = _int("MAX_CONCURRENT_REQUESTS", 512, minimum=1)
LIMITED_EXTRA_DELAY = 0.0
MAX_NEW_ITEMS_PER_CYCLE = _int("MAX_NEW_ITEMS_PER_CYCLE", 1000, minimum=0)
SEARCH_MIN_REQUEST_INTERVAL = _float("SEARCH_MIN_REQUEST_INTERVAL", 0.0, minimum=0.0)
OTHER_MIN_REQUEST_INTERVAL = _float("OTHER_MIN_REQUEST_INTERVAL", 0.0, minimum=0.0)
BUY_MIN_REQUEST_INTERVAL = _float("BUY_MIN_REQUEST_INTERVAL", 0.0, minimum=0.0)
NON_AUTOBUY_CYCLE_EVERY = _int("NON_AUTOBUY_CYCLE_EVERY", 5, minimum=1)

DB_FILE = _cfg("DB_FILE", "/data/bot_data.sqlite" if os.path.isdir("/data") else "bot_data.sqlite")
LZT_SECRET_WORD = _cfg("LZT_SECRET_WORD")
SEED_URLS_JSON = _cfg("SEED_URLS_JSON")

URL_PAGE_SIZE = 12
USER_PAGE_SIZE = 14
MAX_URL_NAME_LEN = 64
TG_SEND_DELAY = _float("TG_SEND_DELAY", 0.01, minimum=0.0)
AUTOBUY_RETRY_ATTEMPTS = _int("AUTOBUY_RETRY_ATTEMPTS", 0, minimum=0)
AUTOBUY_RETRY_MIN_DELAY = _float("AUTOBUY_RETRY_MIN_DELAY", 0.03, minimum=0.0)
AUTOBUY_RETRY_MAX_DELAY = _float("AUTOBUY_RETRY_MAX_DELAY", 0.12, minimum=0.0)
AUTOBUY_QUEUE_RETRY_MIN_DELAY = _float("AUTOBUY_QUEUE_RETRY_MIN_DELAY", 0.06, minimum=0.0)
AUTOBUY_QUEUE_RETRY_MAX_DELAY = _float("AUTOBUY_QUEUE_RETRY_MAX_DELAY", 0.18, minimum=0.0)
FAST_AUTOBUY_TIMEOUT = _float("FAST_AUTOBUY_TIMEOUT", 0.45, minimum=0.2)
AUTOBUY_URL_LIMIT = _int("AUTOBUY_URL_LIMIT", 0, minimum=0)
AUTOBUY_MAX_HTTP_ATTEMPTS = _int("AUTOBUY_MAX_HTTP_ATTEMPTS", 0, minimum=0)
AUTOBUY_PARALLEL_HTTP = _int("AUTOBUY_PARALLEL_HTTP", 24, minimum=1)
AUTOBUY_MAX_DURATION_SEC = _float("AUTOBUY_MAX_DURATION_SEC", 2.8, minimum=0.0)
AUTOBUY_TOTAL_RETRY_WINDOW_SEC = _float("AUTOBUY_TOTAL_RETRY_WINDOW_SEC", 6.0, minimum=0.0)
MAX_ITEMS_PER_SOURCE_SCAN = _int("MAX_ITEMS_PER_SOURCE_SCAN", 200, minimum=0)
AUTOBUY_BURST_FIRST_WAVE = _int("AUTOBUY_BURST_FIRST_WAVE", 24, minimum=1)
USER_ACTION_FETCH_TIMEOUT = _float("USER_ACTION_FETCH_TIMEOUT", 2.4, minimum=0.2)

AUTOBUY_LOG_FILE = _cfg("AUTOBUY_LOG_FILE") or "autobuy.log"
LOG_MAX_BYTES = 15 * 1024 * 1024
LOG_ROTATE_KEEP = 2
BALANCE_CACHE_TTL = 60

__all__ = [
    "API_TOKEN", "LZT_API_KEY", "LZT_BALANCE_ID",
    "OWNER_ID", "OWNER_IDS", "ACCESS_MODE", "ACCESS_OPEN",
    "HUNTER_INTERVAL_BASE", "FETCH_TIMEOUT", "BUY_TIMEOUT",
    "RETRY_MAX", "RETRY_BASE_DELAY", "SHORT_CARD_MAX",
    "ERROR_REPORT_INTERVAL", "MAX_URLS_PER_USER_DEFAULT",
    "MAX_URLS_PER_USER_LIMITED", "MAX_CONCURRENT_REQUESTS",
    "LIMITED_EXTRA_DELAY", "MAX_NEW_ITEMS_PER_CYCLE",
    "SEARCH_MIN_REQUEST_INTERVAL", "OTHER_MIN_REQUEST_INTERVAL",
    "BUY_MIN_REQUEST_INTERVAL", "NON_AUTOBUY_CYCLE_EVERY",
    "DB_FILE", "LZT_SECRET_WORD", "SEED_URLS_JSON",
    "URL_PAGE_SIZE", "USER_PAGE_SIZE", "MAX_URL_NAME_LEN",
    "TG_SEND_DELAY", "AUTOBUY_RETRY_ATTEMPTS",
    "AUTOBUY_RETRY_MIN_DELAY", "AUTOBUY_RETRY_MAX_DELAY",
    "AUTOBUY_QUEUE_RETRY_MIN_DELAY", "AUTOBUY_QUEUE_RETRY_MAX_DELAY",
    "FAST_AUTOBUY_TIMEOUT", "AUTOBUY_URL_LIMIT",
    "AUTOBUY_MAX_HTTP_ATTEMPTS", "AUTOBUY_PARALLEL_HTTP",
    "AUTOBUY_MAX_DURATION_SEC", "AUTOBUY_TOTAL_RETRY_WINDOW_SEC",
    "MAX_ITEMS_PER_SOURCE_SCAN", "AUTOBUY_BURST_FIRST_WAVE",
    "USER_ACTION_FETCH_TIMEOUT", "AUTOBUY_LOG_FILE",
    "LOG_MAX_BYTES", "LOG_ROTATE_KEEP", "BALANCE_CACHE_TTL",
]
