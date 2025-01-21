#!/usr/bin/env python3

import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, MaxNLocator
from pathlib import Path
import sys
from typing import List, Tuple


def load_run_data(run_path: Path, legend_name: str = None) -> Tuple[pd.DataFrame, str]:
    """Load data from a single run directory"""
    # Load metrics CSV
    metrics_df = pd.read_csv(run_path / "metrics.csv")

    # Convert timestamp to datetime in UTC
    metrics_df["timestamp"] = pd.to_datetime(metrics_df["timestamp"]).dt.tz_localize(
        "UTC"
    )

    # Use provided legend name or directory name
    name = legend_name or run_path.name

    return metrics_df, name


def create_comparison_plot(run_data: List[Tuple[pd.DataFrame, str]], output_path: Path):
    """Create a comparison plot of multiple runs"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)

    # Plot each run
    for metrics_df, name in run_data:
        # Calculate relative time from start
        start_time = metrics_df["timestamp"].min()
        metrics_df["seconds"] = (
            metrics_df["timestamp"] - start_time
        ).dt.total_seconds()

        # Plot queue size
        ax1.plot(
            metrics_df["seconds"],
            metrics_df["redis_items"],
            label=f"{name} Queue Size",
            alpha=0.7,
        )

        # Plot processing rate
        processing_rate = (
            -metrics_df["redis_items"].diff() / metrics_df["seconds"].diff()
        )
        smoothed_rate = processing_rate.rolling(window=5).mean()
        ax2.plot(
            metrics_df["seconds"],
            smoothed_rate,
            label=f"{name} Processing Rate",
            alpha=0.7,
        )

    # Configure axes
    ax1.set_xlabel("Time (seconds)")
    ax1.set_ylabel("Number of Items")
    ax1.set_title("Redis Queue Size Over Time (UTC)")
    ax1.grid(True)
    ax1.legend()

    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Items/Second")
    ax2.set_title("Processing Rate Over Time (UTC)")
    ax2.grid(True)
    ax2.legend()

    # Set x-axis ticks every 20 seconds, but limit total ticks
    for ax in [ax1, ax2]:
        # Get current axis range
        x_min, x_max = ax.get_xlim()

        # Calculate appropriate tick interval to stay under 1000 ticks
        range_size = x_max - x_min
        if range_size > 1000:
            major_interval = range_size / 50  # Aim for about 50 major ticks
            minor_interval = major_interval / 4
        else:
            major_interval = 20
            minor_interval = 5

        ax.xaxis.set_major_locator(MultipleLocator(major_interval))
        ax.xaxis.set_minor_locator(MultipleLocator(minor_interval))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x)}"))

        ax.grid(True, which="major", linestyle="-")
        ax.grid(True, which="minor", linestyle=":", alpha=0.5)
        ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()

    plt.show()

    # Save plots
    plt.savefig(output_path / "performance_comparison.png")
    plt.savefig(output_path / "performance_comparison.pdf")
    print(f"Plots saved to: {output_path}/performance_comparison.png/pdf")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare multiple performance test runs"
    )
    parser.add_argument(
        "runs", nargs="+", type=str, help="Paths to run directories to compare"
    )
    parser.add_argument(
        "--names",
        nargs="*",
        type=str,
        help="Names to use in legend (must match number of runs)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="comparison",
        help="Output directory for comparison plots",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Validate inputs
    if args.names and len(args.names) != len(args.runs):
        print("Error: Number of names must match number of runs")
        sys.exit(1)

    # Create output directory
    output_path = Path(args.output)
    output_path.mkdir(exist_ok=True)

    # Load data from each run
    run_data = []
    for i, run_path_str in enumerate(args.runs):
        run_path = Path(run_path_str)
        if not run_path.exists():
            print(f"Error: Run directory not found: {run_path}")
            sys.exit(1)

        name = args.names[i] if args.names else None
        try:
            data = load_run_data(run_path, name)
            run_data.append(data)
        except Exception as e:
            print(f"Error loading data from {run_path}: {e}")
            sys.exit(1)

    # Create comparison plot
    create_comparison_plot(run_data, output_path)


if __name__ == "__main__":
    main()
