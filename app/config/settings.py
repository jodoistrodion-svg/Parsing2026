from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PLACEHOLDER_VALUES = {
    "",
    "replace-with-telegram-bot-token",
    "replace-with-lzt-api-key",
    "replace-with-your-telegram-user-id",
}

_TRUE = {"1", "true", "yes", "on", "enabled", "да"}
_FALSE = {"0", "false", "no", "off", "disabled", "нет"}


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _cfg(name: str, *aliases: str, default: str = "") -> str:
    for candidate in (name, *aliases):
        value = _clean(os.getenv(candidate))
        if value and value.lower() not in _PLACEHOLDER_VALUES:
            return value
    return default


def _int(name: str, *aliases: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _cfg(name, *aliases, default=str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")
    return value


def _float(name: str, *aliases: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = _cfg(name, *aliases, default=str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")
    return value


def _bool(name: str, *aliases: str, default: bool) -> bool:
    raw = _cfg(name, *aliases, default=str(default).lower()).lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ValueError(f"{name} must be a boolean, got {raw!r}")


def _normalize_telegram_token(raw: str | None) -> str:
    token = _clean(raw)
    if token.lower().startswith("bot") and re.match(r"^bot\d{6,12}:", token, flags=re.IGNORECASE):
        token = token[3:]
    return token


@dataclass(frozen=True, slots=True)
class Settings:
    api_token: str
    lzt_api_key: str
    lzt_base_url: str
    lzt_balance_id: int
    lzt_secret_word: str
    credential_encryption_key: str
    owner_id: int
    owner_ids: frozenset[int]
    access_mode: str
    db_file: str
    health_host: str
    health_port: int
    log_level: str
    log_format: str
    dry_run: bool
    autobuy_mode: str
    hunter_interval_base: float
    fetch_timeout: float
    buy_timeout: float
    retry_max: int
    retry_base_delay: float
    retry_max_delay: float
    max_concurrent_requests: int
    max_urls_per_user_default: int
    max_urls_per_user_limited: int
    max_new_items_per_cycle: int
    max_items_per_source_scan: int
    discovery_max_in_flight: int
    non_autobuy_cycle_every: int
    buy_semaphore: int
    autobuy_workers_per_user: int
    autobuy_queue_size: int
    autobuy_retry_attempts: int
    autobuy_retry_min_delay: float
    autobuy_retry_max_delay: float
    autobuy_queue_retry_min_delay: float
    autobuy_queue_retry_max_delay: float
    fast_autobuy_timeout: float
    autobuy_url_limit: int
    autobuy_max_http_attempts: int
    autobuy_parallel_http: int
    autobuy_max_duration_sec: float
    autobuy_total_retry_window_sec: float
    autobuy_burst_first_wave: int
    user_action_fetch_timeout: float
    search_min_request_interval: float
    other_min_request_interval: float
    buy_min_request_interval: float
    db_cleanup_interval_seconds: int
    seen_retention_days: int
    buy_attempt_retention_days: int
    db_busy_timeout_ms: int
    tg_send_delay: float
    url_page_size: int
    user_page_size: int
    max_url_name_len: int
    short_card_max: int
    error_report_interval: int
    tg_startup_probe: bool
    seed_urls_json: str
    autobuy_log_file: str

    @property
    def access_open(self) -> bool:
        return self.access_mode in {"open", "all", "public", "0"}

    def redacted(self) -> dict[str, object]:
        data = asdict(self)
        data["api_token"] = "***" if self.api_token else ""
        data["lzt_api_key"] = "***" if self.lzt_api_key else ""
        data["lzt_secret_word"] = "***" if self.lzt_secret_word else ""
        data["credential_encryption_key"] = "***" if self.credential_encryption_key else ""
        data["owner_ids"] = sorted(self.owner_ids)
        return data


def load_settings() -> Settings:
    owner_id = _int("OWNER_ID", "ADMIN_TELEGRAM_ID", default=0, minimum=0)
    raw_owner_ids = _cfg("OWNER_IDS")
    parsed_owner_ids = {
        int(value.strip())
        for value in raw_owner_ids.split(",")
        if value.strip().lstrip("-").isdigit() and int(value.strip()) > 0
    }
    owner_ids = frozenset(parsed_owner_ids or ({owner_id} if owner_id else set()))

    return Settings(
        api_token=_normalize_telegram_token(
            _cfg("API_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN")
        ),
        lzt_api_key=_cfg("LZT_API_KEY", "LZT_API_TOKEN", "LZT_TOKEN", "LOLZ_API_KEY"),
        lzt_base_url=_cfg("LZT_BASE_URL", default="https://api.lzt.market").rstrip("/"),
        lzt_balance_id=_int("LZT_BALANCE_ID", default=20212, minimum=1),
        lzt_secret_word=_cfg("LZT_SECRET_WORD"),
        credential_encryption_key=_cfg("CREDENTIAL_ENCRYPTION_KEY"),
        owner_id=owner_id,
        owner_ids=owner_ids,
        access_mode=_cfg("ACCESS_MODE", default="closed").lower(),
        db_file=_cfg(
            "DB_FILE",
            default=str(Path("/data/bot_data.sqlite") if Path("/data").is_dir() else Path("bot_data.sqlite")),
        ),
        health_host=_cfg("HEALTH_HOST", default="127.0.0.1"),
        health_port=_int("HEALTH_PORT", default=0, minimum=0, maximum=65535),
        log_level=_cfg("LOG_LEVEL", default="INFO").upper(),
        log_format=_cfg("LOG_FORMAT", default="plain").lower(),
        dry_run=_bool("DRY_RUN", default=False),
        autobuy_mode=_cfg("AUTOBUY_MODE", default="dry-run" if _bool("DRY_RUN", default=False) else "live").lower(),
        hunter_interval_base=_float("HUNTER_INTERVAL_BASE", default=0.02, minimum=0.0),
        fetch_timeout=_float("FETCH_TIMEOUT", default=1.20, minimum=0.2),
        buy_timeout=_float("BUY_TIMEOUT", default=0.32, minimum=0.0),
        retry_max=_int("RETRY_MAX", default=1, minimum=0),
        retry_base_delay=_float("RETRY_BASE_DELAY", default=0.01, minimum=0.0),
        retry_max_delay=_float("RETRY_MAX_DELAY", default=1.5, minimum=0.0),
        max_concurrent_requests=_int("MAX_CONCURRENT_REQUESTS", default=512, minimum=1),
        max_urls_per_user_default=_int("MAX_URLS_PER_USER_DEFAULT", default=50, minimum=1),
        max_urls_per_user_limited=_int("MAX_URLS_PER_USER_LIMITED", default=3, minimum=1),
        max_new_items_per_cycle=_int("MAX_NEW_ITEMS_PER_CYCLE", default=1000, minimum=0),
        max_items_per_source_scan=_int("MAX_ITEMS_PER_SOURCE_SCAN", default=200, minimum=0),
        discovery_max_in_flight=_int("DISCOVERY_MAX_IN_FLIGHT", default=64, minimum=1),
        non_autobuy_cycle_every=_int("NON_AUTOBUY_CYCLE_EVERY", default=5, minimum=1),
        buy_semaphore=_int("BUY_SEMAPHORE", default=128, minimum=1),
        autobuy_workers_per_user=_int("AUTOBUY_WORKERS_PER_USER", default=8, minimum=1),
        autobuy_queue_size=_int("AUTOBUY_QUEUE_SIZE", default=2500, minimum=1),
        autobuy_retry_attempts=_int("AUTOBUY_RETRY_ATTEMPTS", default=0, minimum=0),
        autobuy_retry_min_delay=_float("AUTOBUY_RETRY_MIN_DELAY", default=0.03, minimum=0.0),
        autobuy_retry_max_delay=_float("AUTOBUY_RETRY_MAX_DELAY", default=0.12, minimum=0.0),
        autobuy_queue_retry_min_delay=_float("AUTOBUY_QUEUE_RETRY_MIN_DELAY", default=0.06, minimum=0.0),
        autobuy_queue_retry_max_delay=_float("AUTOBUY_QUEUE_RETRY_MAX_DELAY", default=0.18, minimum=0.0),
        fast_autobuy_timeout=_float("FAST_AUTOBUY_TIMEOUT", default=0.45, minimum=0.2),
        autobuy_url_limit=_int("AUTOBUY_URL_LIMIT", default=0, minimum=0),
        autobuy_max_http_attempts=_int("AUTOBUY_MAX_HTTP_ATTEMPTS", default=2, minimum=0),
        autobuy_parallel_http=_int("AUTOBUY_PARALLEL_HTTP", default=1, minimum=1),
        autobuy_max_duration_sec=_float("AUTOBUY_MAX_DURATION_SEC", default=2.8, minimum=0.0),
        autobuy_total_retry_window_sec=_float("AUTOBUY_TOTAL_RETRY_WINDOW_SEC", default=6.0, minimum=0.0),
        autobuy_burst_first_wave=_int("AUTOBUY_BURST_FIRST_WAVE", default=1, minimum=1),
        user_action_fetch_timeout=_float("USER_ACTION_FETCH_TIMEOUT", default=2.4, minimum=0.2),
        search_min_request_interval=_float("SEARCH_MIN_REQUEST_INTERVAL", default=3.0, minimum=0.0),
        other_min_request_interval=_float("OTHER_MIN_REQUEST_INTERVAL", default=0.2, minimum=0.0),
        buy_min_request_interval=_float("BUY_MIN_REQUEST_INTERVAL", default=0.2, minimum=0.0),
        db_cleanup_interval_seconds=_int("DB_CLEANUP_INTERVAL_SECONDS", default=3600, minimum=60),
        seen_retention_days=_int("SEEN_RETENTION_DAYS", default=90, minimum=1),
        buy_attempt_retention_days=_int("BUY_ATTEMPT_RETENTION_DAYS", default=180, minimum=1),
        db_busy_timeout_ms=_int("DB_BUSY_TIMEOUT_MS", default=5000, minimum=100),
        tg_send_delay=_float("TG_SEND_DELAY", default=0.01, minimum=0.0),
        url_page_size=_int("URL_PAGE_SIZE", default=12, minimum=1),
        user_page_size=_int("USER_PAGE_SIZE", default=14, minimum=1),
        max_url_name_len=_int("MAX_URL_NAME_LEN", default=64, minimum=8),
        short_card_max=3200,
        error_report_interval=3600,
        tg_startup_probe=_bool("TG_STARTUP_PROBE", default=False),
        seed_urls_json=_cfg("SEED_URLS_JSON"),
        autobuy_log_file=_cfg("AUTOBUY_LOG_FILE", default="autobuy.log"),
    )


settings = load_settings()

API_TOKEN = settings.api_token
LZT_API_KEY = settings.lzt_api_key
LZT_BASE_URL = settings.lzt_base_url
LZT_BALANCE_ID = settings.lzt_balance_id
LZT_SECRET_WORD = settings.lzt_secret_word
CREDENTIAL_ENCRYPTION_KEY = settings.credential_encryption_key
OWNER_ID = settings.owner_id
OWNER_IDS = set(settings.owner_ids)
ACCESS_MODE = settings.access_mode
ACCESS_OPEN = settings.access_open
HUNTER_INTERVAL_BASE = settings.hunter_interval_base
FETCH_TIMEOUT = settings.fetch_timeout
BUY_TIMEOUT = settings.buy_timeout
RETRY_MAX = settings.retry_max
RETRY_BASE_DELAY = settings.retry_base_delay
RETRY_MAX_DELAY = settings.retry_max_delay
MAX_CONCURRENT_REQUESTS = settings.max_concurrent_requests
MAX_URLS_PER_USER_DEFAULT = settings.max_urls_per_user_default
MAX_URLS_PER_USER_LIMITED = settings.max_urls_per_user_limited
LIMITED_EXTRA_DELAY = 0.0
MAX_NEW_ITEMS_PER_CYCLE = settings.max_new_items_per_cycle
MAX_ITEMS_PER_SOURCE_SCAN = settings.max_items_per_source_scan
DISCOVERY_MAX_IN_FLIGHT = settings.discovery_max_in_flight
SEARCH_MIN_REQUEST_INTERVAL = settings.search_min_request_interval
OTHER_MIN_REQUEST_INTERVAL = settings.other_min_request_interval
BUY_MIN_REQUEST_INTERVAL = settings.buy_min_request_interval
NON_AUTOBUY_CYCLE_EVERY = settings.non_autobuy_cycle_every
BUY_SEMAPHORE = settings.buy_semaphore
AUTOBUY_WORKERS_PER_USER = settings.autobuy_workers_per_user
AUTOBUY_QUEUE_SIZE = settings.autobuy_queue_size
AUTOBUY_RETRY_ATTEMPTS = settings.autobuy_retry_attempts
AUTOBUY_RETRY_MIN_DELAY = settings.autobuy_retry_min_delay
AUTOBUY_RETRY_MAX_DELAY = settings.autobuy_retry_max_delay
AUTOBUY_QUEUE_RETRY_MIN_DELAY = settings.autobuy_queue_retry_min_delay
AUTOBUY_QUEUE_RETRY_MAX_DELAY = settings.autobuy_queue_retry_max_delay
FAST_AUTOBUY_TIMEOUT = settings.fast_autobuy_timeout
AUTOBUY_URL_LIMIT = settings.autobuy_url_limit
AUTOBUY_MAX_HTTP_ATTEMPTS = settings.autobuy_max_http_attempts
AUTOBUY_PARALLEL_HTTP = settings.autobuy_parallel_http
AUTOBUY_MAX_DURATION_SEC = settings.autobuy_max_duration_sec
AUTOBUY_TOTAL_RETRY_WINDOW_SEC = settings.autobuy_total_retry_window_sec
AUTOBUY_BURST_FIRST_WAVE = settings.autobuy_burst_first_wave
USER_ACTION_FETCH_TIMEOUT = settings.user_action_fetch_timeout
DB_FILE = settings.db_file
DB_CLEANUP_INTERVAL_SECONDS = settings.db_cleanup_interval_seconds
SEEN_RETENTION_DAYS = settings.seen_retention_days
BUY_ATTEMPT_RETENTION_DAYS = settings.buy_attempt_retention_days
DB_BUSY_TIMEOUT_MS = settings.db_busy_timeout_ms
TG_SEND_DELAY = settings.tg_send_delay
URL_PAGE_SIZE = settings.url_page_size
USER_PAGE_SIZE = settings.user_page_size
MAX_URL_NAME_LEN = settings.max_url_name_len
SHORT_CARD_MAX = settings.short_card_max
ERROR_REPORT_INTERVAL = settings.error_report_interval
AUTOBUY_LOG_FILE = settings.autobuy_log_file
TG_STARTUP_PROBE = settings.tg_startup_probe
LOG_MAX_BYTES = 15 * 1024 * 1024
LOG_ROTATE_KEEP = 2
BALANCE_CACHE_TTL = 60
HEALTH_HOST = settings.health_host
HEALTH_PORT = settings.health_port
LOG_LEVEL = settings.log_level
LOG_FORMAT = settings.log_format
DRY_RUN = settings.dry_run
AUTOBUY_MODE = settings.autobuy_mode
SEED_URLS_JSON = settings.seed_urls_json
FAST_AUTOBUY_TIMEOUT = settings.fast_autobuy_timeout


def validate_runtime_config() -> None:
    errors: list[str] = []
    if not API_TOKEN:
        errors.append("API_TOKEN is missing (accepted aliases: TELEGRAM_BOT_TOKEN, BOT_TOKEN)")
    if not ACCESS_OPEN and not OWNER_IDS:
        errors.append("OWNER_ID/OWNER_IDS is required when ACCESS_MODE=closed (legacy alias: ADMIN_TELEGRAM_ID)")
    if ACCESS_MODE not in {"closed", "open", "all", "public", "0"}:
        errors.append(f"ACCESS_MODE has unsupported value: {ACCESS_MODE!r}")
    if LOG_FORMAT not in {"plain", "json"}:
        errors.append("LOG_FORMAT must be 'plain' or 'json'")
    if AUTOBUY_MODE not in {"live", "dry-run"}:
        errors.append("AUTOBUY_MODE must be 'live' or 'dry-run'")
    if LZT_BASE_URL not in {
        "https://api.lzt.market",
    }:
        errors.append("LZT_BASE_URL must point to an allowed LZT API host")
    if errors:
        raise RuntimeError("; ".join(errors))


def describe_runtime_config() -> dict[str, object]:
    return settings.redacted()


__all__ = [
    name
    for name in globals()
    if name.isupper() or name in {"Settings", "settings", "load_settings", "validate_runtime_config", "describe_runtime_config"}
]