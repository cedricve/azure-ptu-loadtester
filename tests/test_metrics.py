import pytest

from azure_ptu_loadtester.metrics import percentile, summarize
from azure_ptu_loadtester.runner import RequestResult


def result(latency_ms: float, success: bool = True) -> RequestResult:
    return RequestResult(
        endpoint="model-a",
        sequence=1,
        scheduled_offset_ms=0.0,
        queue_delay_ms=2.0,
        latency_ms=latency_ms,
        status=200 if success else 429,
        success=success,
        error=None if success else "HTTP 429",
    )


def test_percentile_interpolates_between_samples():
    assert percentile([10.0, 20.0, 30.0, 40.0], 0.95) == pytest.approx(38.5)
    assert percentile([], 0.95) is None


def test_summary_excludes_failures_from_latency():
    summary = summarize([result(10.0), result(20.0), result(500.0, False)], 1.0)

    assert summary["attempted"] == 3
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    assert summary["latency_ms"]["mean"] == 15.0
    assert summary["latency_ms"]["max"] == 20.0
    assert summary["failures"] == {"HTTP 429": 1}