"""
AOP-style performance monitoring for service-layer calls (course req #10).

Mirrors Spring's PerformanceMonitorAspect: logs execution time and aggregates
stats for bottleneck analysis reports.
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from typing import Any, Callable, TypeVar

from django.conf import settings

logger = logging.getLogger('performance')

_stats_lock = threading.Lock()
_stats: dict[str, list[float]] = {}
_MAX_SAMPLES_PER_LABEL = 10_000

F = TypeVar('F', bound=Callable[..., Any])


def _enabled() -> bool:
    return getattr(settings, 'PERFORMANCE_MONITOR_ENABLED', True)


def _record(label: str, elapsed_ms: float) -> None:
    with _stats_lock:
        bucket = _stats.setdefault(label, [])
        bucket.append(elapsed_ms)
        if len(bucket) > _MAX_SAMPLES_PER_LABEL:
            del bucket[: len(bucket) - _MAX_SAMPLES_PER_LABEL]


def reset_stats() -> None:
    with _stats_lock:
        _stats.clear()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(index, len(ordered) - 1))]


def get_stats_snapshot() -> dict[str, dict[str, float | int]]:
    with _stats_lock:
        labels = {label: list(samples) for label, samples in _stats.items()}

    snapshot: dict[str, dict[str, float | int]] = {}
    for label, samples in labels.items():
        if not samples:
            continue
        snapshot[label] = {
            'count': len(samples),
            'mean_ms': round(sum(samples) / len(samples), 2),
            'median_ms': round(_percentile(samples, 50), 2),
            'p95_ms': round(_percentile(samples, 95), 2),
            'max_ms': round(max(samples), 2),
        }
    return snapshot


def monitor_execution(name: str | None = None) -> Callable[[F], F]:
    """Decorator equivalent to Spring @Around on core.service.* methods."""

    def decorator(func: F) -> F:
        label = name or f'{func.__module__}.{func.__qualname__}'

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _enabled():
                return func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                _record(label, elapsed_ms)
                threshold = getattr(settings, 'PERFORMANCE_MONITOR_SLOW_MS', 200)
                if elapsed_ms >= threshold:
                    logger.warning('%s executed in %.2fms (slow)', label, elapsed_ms)
                else:
                    logger.info('%s executed in %.2fms', label, elapsed_ms)

        return wrapper  # type: ignore[return-value]

    return decorator
