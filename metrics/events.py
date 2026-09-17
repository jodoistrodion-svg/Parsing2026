from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True, slots=True)
class LatencyEvent:
    name: str
    elapsed_ms: int


def elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))
