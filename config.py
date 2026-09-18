"""Backward-compatible configuration facade.

New code should import settings from app.config.settings.
"""

from os import getenv

from app.config.settings import API_TOKEN, LZT_API_KEY

LZT_URL = (getenv("LZT_URL") or "https://api.lzt.market/category/mihoyo?sort_by=date&order=desc").strip()
try:
    CHECK_INTERVAL = int((getenv("CHECK_INTERVAL") or "5").strip())
except ValueError as exc:
    raise ValueError("CHECK_INTERVAL must be an integer") from exc

__all__ = ["API_TOKEN", "LZT_API_KEY", "LZT_URL", "CHECK_INTERVAL"]
