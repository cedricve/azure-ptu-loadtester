from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import ConfigError, load_endpoints
from .metrics import summarize
from .reports import write_reports
from .runner import EndpointRun, RunOptions, run_comparison


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two Azure OpenAI endpoints under equal request load."
    )
    parser.add_argument("--config", default="loadtest.toml", help="Endpoint TOML file")
    parser.add_argument(
        "--rps",
        required=True,
        type=_positive_float,
        help="Requests per second sent to each endpoint",
    )
    parser.add_argument(
        "--duration",
        type=_positive_float,
        default=30.0,
        help="Load duration in seconds (default: 30)",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: OK",
        help="User prompt sent in every request",
    )
    parser.add_argument(
        "--max-tokens",
        type=_positive_int,
        default=32,
        help="Maximum response tokens (default: 32)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=120.0,
        help="Per-request timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=_positive_int,
        default=100,
        help="Maximum in-flight requests per endpoint (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory for JSON and CSV reports (default: results)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()

    try:
        endpoints = load_endpoints(arguments.config)
    except ConfigError as error:
        parser.error(str(error))

    options = RunOptions(
        rps=arguments.rps,
        duration_seconds=arguments.duration,
        prompt=arguments.prompt,
        max_tokens=arguments.max_tokens,
        timeout_seconds=arguments.timeout,
        max_concurrency=arguments.max_concurrency,
    )

    total_rps = options.rps * len(endpoints)
    print(
        f"Running {options.rps:g} RPS per endpoint ({total_rps:g} total) "
        f"for {options.duration_seconds:g}s..."
    )
    try:
        runs = asyncio.run(run_comparison(endpoints, options))
    except KeyboardInterrupt:
        parser.exit(130, "Load test interrupted.\n")

    _print_summary(runs)
    json_path, csv_path = write_reports(runs, options, arguments.output_dir)
    print(f"\nReports: {json_path} and {csv_path}")


def _print_summary(runs: tuple[EndpointRun, EndpointRun]) -> None:
    headers = ("Endpoint", "Success", "Mean", "p50", "p95", "p99", "Max", "Queue p95")
    rows = []
    for run in runs:
        summary = summarize(run.results, run.elapsed_seconds)
        latency = summary["latency_ms"]
        queue_delay = summary["queue_delay_ms"]
        assert isinstance(latency, dict)
        assert isinstance(queue_delay, dict)
        rows.append(
            (
                run.endpoint.name,
                f"{summary['succeeded']}/{summary['attempted']}",
                _milliseconds(latency["mean"]),
                _milliseconds(latency["p50"]),
                _milliseconds(latency["p95"]),
                _milliseconds(latency["p99"]),
                _milliseconds(latency["max"]),
                _milliseconds(queue_delay["p95"]),
            )
        )

    widths = [max(len(str(value)) for value in column) for column in zip(headers, *rows)]
    print()
    print("  ".join(str(value).ljust(width) for value, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))


def _milliseconds(value: object) -> str:
    return "-" if value is None else f"{float(value):.1f} ms"


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


if __name__ == "__main__":
    main()