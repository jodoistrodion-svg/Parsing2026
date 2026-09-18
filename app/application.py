"""Application composition root for Parsing2026."""

from app.runtime.core import *
from app.purchase.autobuy import *
from app import handlers as _handlers

__all__ = [name for name in globals() if not name.startswith("__")]
