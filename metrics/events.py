from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Mapping


def _label_key(labels: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _prom_name(name: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
    return safe.lower().strip("_") or "metric"


class MetricsRegistry:
    """Small dependency-free metrics registry with Prometheus exposition."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._observations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}

    def inc(self, name: str, value: int = 1, labels: Mapping[str, object] | None = None) -> None:
        key = (_prom_name(name), _label_key(labels))
        with self._lock:
            self._counters[key] += int(value)

    def set(self, name: str, value: float, labels: Mapping[str, object] | None = None) -> None:
        key = (_prom_name(name), _label_key(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, labels: Mapping[str, object] | None = None) -> None:
        key = (_prom_name(name), _label_key(labels))
        with self._lock:
            bucket = self._observations.setdefault(key, [])
            bucket.append(float(value))
            if len(bucket) > 2048:
                del bucket[: len(bucket) - 2048]

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "observations": {key: list(values) for key, values in self._observations.items()},
            }

    def prometheus_text(self) -> str:
        lines: list[str] = []
        snap = self.snapshot()
        for (name, labels), value in sorted(snap["counters"].items()):
            lines.append(f"{name}_total{self._format_labels(labels)} {value}")
        for (name, labels), value in sorted(snap["gauges"].items()):
            lines.append(f"{name}{self._format_labels(labels)} {value}")
        for (name, labels), values in sorted(snap["observations"].items()):
            if values:
                lines.append(f"{name}_count{self._format_labels(labels)} {len(values)}")
                lines.append(f"{name}_sum{self._format_labels(labels)} {sum(values):.3f}")
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        encoded = []
        for key, value in labels:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            encoded.append(f'{key}="{escaped}"')
        return "{" + ",".join(encoded) + "}"


METRICS = MetricsRegistry()


@dataclass(frozen=True, slots=True)
class LatencyEvent:
    operation: str
    elapsed_ms: int


def elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)
