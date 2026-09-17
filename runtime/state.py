from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class UserRuntimeState:
    user_id: int
    hunter_active: bool = False
    search_active: bool = False
    seen_items: set[str] = field(default_factory=set)
    buy_attempted: set[str] = field(default_factory=set)
