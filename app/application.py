"""Application composition root for Parsing2026."""

from app.config.settings import API_TOKEN, LZT_BALANCE_ID
from app.runtime.core import autobuy_queue_manager, dp, has_valid_telegram_token, logger, _safe_compact
from app.purchase import autobuy as _autobuy
from app import handlers as _handlers

# These imports register aiogram handlers and autobuy helpers at module import time.
_BOOTSTRAPPED_MODULES = (_autobuy, _handlers)

__all__ = [
    "API_TOKEN", "LZT_BALANCE_ID", "autobuy_queue_manager", "dp",
    "has_valid_telegram_token", "logger", "_safe_compact",
]
