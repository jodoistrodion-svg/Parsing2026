from __future__ import annotations

import os
import re
from collections import defaultdict

from config import API_TOKEN as _API_TOKEN, LZT_API_KEY as _LZT_API_KEY


def _normalize_telegram_token(raw: str | None) -> str:
    token = (raw or "").strip().strip('"').strip("'")
    if token.lower().startswith("bot") and re.match(r"^bot\d{6,12}:", token, flags=re.IGNORECASE):
        token = token[3:]
    return token


def _cfg(name: str, fallback: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else fallback


API_TOKEN = _normalize_telegram_token(_cfg("API_TOKEN", _API_TOKEN))
LZT_API_KEY = _cfg("LZT_API_KEY", _LZT_API_KEY)
LZT_BALANCE_ID = int((_cfg("LZT_BALANCE_ID", "20212") or "20212").strip())

OWNER_ID = int((_cfg("OWNER_ID") or "0").strip())
OWNER_IDS = {int(x.strip()) for x in (_cfg("OWNER_IDS") or "").split(",") if x.strip().lstrip("-").isdigit()} or {OWNER_ID}
ACCESS_MODE = (_cfg("ACCESS_MODE") or "closed").strip().lower()
ACCESS_OPEN = ACCESS_MODE in {"open", "all", "public", "0"}

HUNTER_INTERVAL_BASE = float(_cfg("HUNTER_INTERVAL_BASE", "0.02"))
FETCH_TIMEOUT = float(_cfg("FETCH_TIMEOUT", "1.20"))
BUY_TIMEOUT = float(_cfg("BUY_TIMEOUT", "0.32"))
RETRY_MAX = int(_cfg("RETRY_MAX", "1"))
RETRY_BASE_DELAY = float(_cfg("RETRY_BASE_DELAY", "0.01"))

SHORT_CARD_MAX = 3200
ERROR_REPORT_INTERVAL = 3600
MAX_URLS_PER_USER_DEFAULT = 50
MAX_URLS_PER_USER_LIMITED = 3
MAX_CONCURRENT_REQUESTS = int(_cfg("MAX_CONCURRENT_REQUESTS", "512"))
LIMITED_EXTRA_DELAY = 0.0
MAX_NEW_ITEMS_PER_CYCLE = int(_cfg("MAX_NEW_ITEMS_PER_CYCLE", "1000"))
SEARCH_MIN_REQUEST_INTERVAL = float(_cfg("SEARCH_MIN_REQUEST_INTERVAL", "0.0"))
OTHER_MIN_REQUEST_INTERVAL = float(_cfg("OTHER_MIN_REQUEST_INTERVAL", "0.0"))
BUY_MIN_REQUEST_INTERVAL = float(_cfg("BUY_MIN_REQUEST_INTERVAL", "0.0"))
NON_AUTOBUY_CYCLE_EVERY = int(_cfg("NON_AUTOBUY_CYCLE_EVERY", "5"))

DB_FILE = _cfg("DB_FILE", "/data/bot_data.sqlite" if os.path.isdir("/data") else "bot_data.sqlite")
LZT_SECRET_WORD = _cfg("LZT_SECRET_WORD").strip()
SEED_URLS_JSON = _cfg("SEED_URLS_JSON").strip()

URL_PAGE_SIZE = 12
USER_PAGE_SIZE = 14
MAX_URL_NAME_LEN = 64
TG_SEND_DELAY = float(_cfg("TG_SEND_DELAY", "0.01"))
AUTOBUY_RETRY_ATTEMPTS = int(_cfg("AUTOBUY_RETRY_ATTEMPTS", "0"))
AUTOBUY_RETRY_MIN_DELAY = float(_cfg("AUTOBUY_RETRY_MIN_DELAY", "0.03"))
AUTOBUY_RETRY_MAX_DELAY = float(_cfg("AUTOBUY_RETRY_MAX_DELAY", "0.12"))
AUTOBUY_QUEUE_RETRY_MIN_DELAY = float(_cfg("AUTOBUY_QUEUE_RETRY_MIN_DELAY", "0.06"))
AUTOBUY_QUEUE_RETRY_MAX_DELAY = float(_cfg("AUTOBUY_QUEUE_RETRY_MAX_DELAY", "0.18"))
FAST_AUTOBUY_TIMEOUT = float(_cfg("FAST_AUTOBUY_TIMEOUT", "0.45"))
AUTOBUY_URL_LIMIT = int(_cfg("AUTOBUY_URL_LIMIT", "0"))
AUTOBUY_MAX_HTTP_ATTEMPTS = int(_cfg("AUTOBUY_MAX_HTTP_ATTEMPTS", "0"))
AUTOBUY_PARALLEL_HTTP = int(_cfg("AUTOBUY_PARALLEL_HTTP", "24"))
AUTOBUY_MAX_DURATION_SEC = float(_cfg("AUTOBUY_MAX_DURATION_SEC", "2.8"))
AUTOBUY_TOTAL_RETRY_WINDOW_SEC = float(_cfg("AUTOBUY_TOTAL_RETRY_WINDOW_SEC", "6.0"))
MAX_ITEMS_PER_SOURCE_SCAN = int(_cfg("MAX_ITEMS_PER_SOURCE_SCAN", "200"))
AUTOBUY_BURST_FIRST_WAVE = int(_cfg("AUTOBUY_BURST_FIRST_WAVE", "24"))
USER_ACTION_FETCH_TIMEOUT = float(_cfg("USER_ACTION_FETCH_TIMEOUT", "2.4"))

AUTOBUY_LOG_FILE = _cfg("AUTOBUY_LOG_FILE") or "autobuy.log"
LOG_MAX_BYTES = 15 * 1024 * 1024
LOG_ROTATE_KEEP = 2
BALANCE_CACHE_TTL = 60

__all__ = [name for name in globals() if not name.startswith("__")]
