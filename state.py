from __future__ import annotations
from dataclasses import dataclass,field
@dataclass(slots=True)
class UserRuntimeState:
    hunter_active:bool=False
    mode:str="off"
    seen:set[str]=field(default_factory=set)
    attempted:set[str]=field(default_factory=set)
    inflight:set[str]=field(default_factory=set)
    api_errors:int=0
