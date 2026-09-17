from __future__ import annotations
from dataclasses import dataclass
from time import perf_counter
@dataclass(frozen=True,slots=True)
class LatencyEvent:
    operation:str
    elapsed_ms:int
def elapsed_ms(start:float)->int:return int((perf_counter()-start)*1000)
