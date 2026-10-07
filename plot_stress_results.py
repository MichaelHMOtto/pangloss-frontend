import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_results(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    numeric_fields = [
        "total_requests",
        "successful_requests",
        "failed_requests",
        "concurrency",
        "duration_seconds",
        "requests_per_second_total",
        "requests_per_second_successful",
        "latency_median_seconds",
        "latency_p95_seconds",
        "latency_p99_seconds",
    ]

    for row in rows:
        for field in numeric_fields:
            row[field] = float(row[field])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("stress-results.png"),
    )
    args = parser.parse_args()

    rows = load_results(args.csv_file)
    positions = list(range(len(rows)))
    labels = [
        f"{int(row['total_requests'])}\nc={int(row['concurrency'])}"
        for row in rows
    ]

    success_rates = [
        row["successful_requests"] / row["total_requests"] * 100
        for row in rows
    ]

    fig, axes = plt.subplots(3, 1, figsize=(14, 12), constrained_layout=True)

    # Success rate
    colors = [
        "#27864a" if rate == 100 else "#c6413a"
        for rate in success_rates
    ]
    axes[0].bar(positions, success_rates, color=colors)
    axes[0].axhline(100, color="#222222", linewidth=1)
    axes[0].set_ylabel("Success rate (%)")
    axes[0].set_ylim(0, 105)
    axes[0].set_title("Successful workflows")

    for position, rate in zip(positions, success_rates):
        axes[0].text(
            position,
            min(rate + 2, 101),
            f"{rate:.1f}%",
            ha="center",
            fontsize=8,
        )

    # Throughput
    axes[1].plot(
        positions,
        [row["requests_per_second_total"] for row in rows],
        marker="o",
        label="Attempted workflows/s",
        color="#376fba",
    )
    axes[1].plot(
        positions,
        [row["requests_per_second_successful"] for row in rows],
        marker="o",
        label="Successful workflows/s",
        color="#27864a",
    )
    axes[1].set_ylabel("Workflows per second")
    axes[1].set_title("Throughput")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.25)

    # Latency percentiles
    axes[2].plot(
        positions,
        [row["latency_median_seconds"] for row in rows],
        marker="o",
        label="Median",
    )
    axes[2].plot(
        positions,
        [row["latency_p95_seconds"] for row in rows],
        marker="o",
        label="p95",
    )
    axes[2].plot(
        positions,
        [row["latency_p99_seconds"] for row in rows],
        marker="o",
        label="p99",
    )
    axes[2].set_ylabel("Seconds")
    axes[2].set_title("Workflow latency")
    axes[2].legend()
    axes[2].grid(axis="y", alpha=0.25)

    for axis in axes:
        axis.set_xticks(positions, labels)
        axis.set_xlabel("Total workflows / concurrency")

    fig.suptitle("Pangloss Complex Create/Update Stress Test", fontsize=16)
    fig.savefig(args.output, dpi=160)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
    