from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def _values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(v).strip().lower() for v in value if str(v).strip())
    text = str(value).strip().lower()
    return (text,) if text else ()


def _item_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip().lower()
    return ""


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class FilterSpec:
    include_title: tuple[str, ...] = field(default_factory=tuple)
    exclude_title: tuple[str, ...] = field(default_factory=tuple)
    price_min: float | None = None
    price_max: float | None = None
    region: tuple[str, ...] = field(default_factory=tuple)
    email_provider: tuple[str, ...] = field(default_factory=tuple)
    email_type: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "include_title", _values(self.include_title))
        object.__setattr__(self, "exclude_title", _values(self.exclude_title))
        object.__setattr__(self, "region", _values(self.region))
        object.__setattr__(self, "email_provider", _values(self.email_provider))
        object.__setattr__(self, "email_type", _values(self.email_type))


class FilterEngine:
    """Cheap synchronous filters for the discovery hot path."""

    def __init__(self, spec: FilterSpec | None = None):
        self.spec = spec or FilterSpec()

    def accept(self, item: dict[str, Any]) -> bool:
        return matches_filter(item, self.spec)


def matches_filter(item: dict[str, Any], spec: FilterSpec) -> bool:
    title = _item_text(item, "title", "name")
    if spec.include_title and not any(term in title for term in spec.include_title):
        return False
    if spec.exclude_title and any(term in title for term in spec.exclude_title):
        return False

    price = _number(item.get("price"))
    if spec.price_min is not None and (price is None or price < spec.price_min):
        return False
    if spec.price_max is not None and (price is None or price > spec.price_max):
        return False

    if spec.region:
        region = _item_text(item, "region", "country")
        if not any(value == region or value in region for value in spec.region):
            return False

    if spec.email_provider:
        provider = _item_text(item, "email_provider", "email")
        if not any(value == provider or value in provider for value in spec.email_provider):
            return False

    if spec.email_type:
        email_type = _item_text(item, "email_type")
        if not any(value == email_type or value in email_type for value in spec.email_type):
            return False

    return True
