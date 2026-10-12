from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .metrics import summarize
from .runner import EndpointRun, RunOptions


def write_reports(
    runs: tuple[EndpointRun, EndpointRun],
    options: RunOptions,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = destination / f"loadtest-{timestamp}.json"
    csv_path = destination / f"loadtest-{timestamp}.csv"

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "options": {
            "rps_per_endpoint": options.rps,
            "duration_seconds": options.duration_seconds,
            "max_tokens": options.max_tokens,
            "timeout_seconds": options.timeout_seconds,
            "max_concurrency": options.max_concurrency,
            "prompt_sha256": hashlib.sha256(options.prompt.encode()).hexdigest(),
        },
        "endpoints": [
            {
                "config": run.endpoint.public_dict(),
                "elapsed_seconds": run.elapsed_seconds,
                "summary": summarize(run.results, run.elapsed_seconds),
                "requests": [asdict(result) for result in run.results],
            }
            for run in runs
        ],
    }
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    fieldnames = list(asdict(runs[0].results[0]).keys()) if runs[0].results else []
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            writer.writerows(asdict(result) for result in run.results)

    return json_path, csv_path