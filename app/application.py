"""Application composition root for Parsing2026."""

from app.runtime.core import API_TOKEN, LZT_BALANCE_ID, autobuy_queue_manager, dp, has_valid_telegram_token, logger, _safe_compact
from app.purchase import autobuy as _autobuy
from app import handlers as _handlers

__all__ = [
    "API_TOKEN", "LZT_BALANCE_ID", "autobuy_queue_manager", "dp",
    "has_valid_telegram_token", "logger", "_safe_compact",
]
