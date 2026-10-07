# tests/test_stress/stats.py

import csv
import json
import os
import statistics
import time
from pathlib import Path


def build_stress_stats(
    name: str,
    *,
    total: int,
    concurrency: int,
    duration: float,
    latencies: list[float],
    extra: dict | None = None,
) -> dict:
    if not latencies:
        raise ValueError("Cannot build stress stats without successful latencies")

    latencies_sorted = sorted(latencies)

    def percentile(p: float) -> float:
        index = int((len(latencies_sorted) - 1) * p)
        return latencies_sorted[index]

    successful_requests = len(latencies)

    stats = {
        "name": name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_requests": total,
        "successful_requests": successful_requests,
        "failed_requests": total - successful_requests,
        "concurrency": concurrency,
        "duration_seconds": duration,
        "requests_per_second_total": total / duration,
        "requests_per_second_successful": successful_requests / duration,
        "latency_avg_seconds": statistics.mean(latencies),
        "latency_median_seconds": statistics.median(latencies),
        "latency_p95_seconds": percentile(0.95),
        "latency_p99_seconds": percentile(0.99),
        "latency_max_seconds": max(latencies),
        "latency_min_seconds": min(latencies),
    }

    if extra:
        extra = extra.copy()

        if "error_counts" in extra:
            extra["error_counts"] = json.dumps(extra["error_counts"])

        stats.update(extra)

    return stats


def write_stress_stats(
    name: str,
    *,
    total: int,
    concurrency: int,
    duration: float,
    latencies: list[float],
    extra: dict | None = None,
):
    output_dir = Path(os.environ.get("PANGLOSS_STRESS_OUTPUT_DIR", "stress-results"))
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = build_stress_stats(
        name,
        total=total,
        concurrency=concurrency,
        duration=duration,
        latencies=latencies,
        extra=extra,
    )

    json_file = (
        output_dir
        / f"{name}-{total}req-{concurrency}conc-{int(time.time())}.json"
    )
    json_file.write_text(json.dumps(stats, indent=2))

    csv_file = output_dir / f"{name}-results.csv"
    file_exists = csv_file.exists()

    with csv_file.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(stats.keys()))

        if not file_exists:
            writer.writeheader()

        writer.writerow(stats)

    print(json.dumps(stats, indent=2))
    print(f"Wrote CSV row to: {csv_file}")