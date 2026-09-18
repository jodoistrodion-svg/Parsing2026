from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable

def _text(value: Any) -> str:
    return str(value if value is not None else "").strip().lower()
def _number(value: Any) -> float | None:
    try:
        if value in (None, "", "—"): return None
        return float(value)
    except (TypeError, ValueError): return None
def _values(item: dict[str, Any], key: str) -> list[str]:
    value=item.get(key)
    if isinstance(value,(list,tuple,set)): return [_text(v) for v in value]
    if value in (None,""): return []
    return [_text(value)]

@dataclass(frozen=True, slots=True)
class FilterSpec:
    include_title: tuple[str,...]=()
    exclude_title: tuple[str,...]=()
    price_min: float|None=None
    price_max: float|None=None
    region: tuple[str,...]=()
    email_provider: tuple[str,...]=()
    email_type: tuple[str,...]=()
    @classmethod
    def from_dict(cls,data:dict[str,Any]|None)->"FilterSpec":
        data=data or {}
        def many(name:str)->tuple[str,...]:
            value=data.get(name,())
            if isinstance(value,str): value=(value,)
            return tuple(x for x in (_text(v) for v in value or ()) if x)
        return cls(many("include_title"),many("exclude_title"),_number(data.get("price_min")),_number(data.get("price_max")),many("region"),many("email_provider"),many("email_type"))

def matches_filter(item:dict[str,Any],spec:FilterSpec)->bool:
    title=_text(item.get("title"))
    if spec.include_title and not any(t in title for t in spec.include_title): return False
    if spec.exclude_title and any(t in title for t in spec.exclude_title): return False
    price=_number(item.get("price"))
    if spec.price_min is not None and (price is None or price<spec.price_min): return False
    if spec.price_max is not None and (price is None or price>spec.price_max): return False
    if spec.region:
        regions=_values(item,"region")+_values(item,"country")
        if not any(w in regions for w in spec.region): return False
    if spec.email_provider and not any(w in _values(item,"email_provider") for w in spec.email_provider): return False
    if spec.email_type and not any(w in _values(item,"email_type") for w in spec.email_type): return False
    return True

@dataclass(slots=True)
class FilterEngine:
    spec: FilterSpec=field(default_factory=FilterSpec)
    def accept(self,item:dict[str,Any])->bool: return matches_filter(item,self.spec)
    def filter(self,items:Iterable[dict[str,Any]])->list[dict[str,Any]]: return [i for i in items if self.accept(i)]
