from __future__ import annotations

from collections import Counter
from statistics import fmean
from typing import Iterable

from .runner import RequestResult


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None

    position = (len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def summarize(results: list[RequestResult], elapsed_seconds: float) -> dict[str, object]:
    successful = [result for result in results if result.success]
    latencies = [result.latency_ms for result in successful]
    queue_delays = [result.queue_delay_ms for result in results]
    failure_types = Counter(
        result.error or f"HTTP {result.status}" for result in results if not result.success
    )

    attempted = len(results)
    succeeded = len(successful)
    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": attempted - succeeded,
        "success_rate_pct": succeeded / attempted * 100 if attempted else 0.0,
        "completion_rps": attempted / elapsed_seconds if elapsed_seconds else 0.0,
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "mean": fmean(latencies) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies) if latencies else None,
        },
        "queue_delay_ms": {
            "mean": fmean(queue_delays) if queue_delays else None,
            "p95": percentile(queue_delays, 0.95),
            "max": max(queue_delays) if queue_delays else None,
        },
        "failures": dict(failure_types),
    }