import pandas as pd
import matplotlib.pyplot as plt
import ast
import numpy as np
from datetime import datetime
import re

# List of CSV files to process - EDIT THIS LIST
csv_files = ["data/yellow-goat_2025-01-07_12-41PM_metrics.csv"]


def extract_running_total_requests(row_str):
    """Extract running_total_requests from the complex string format"""
    if pd.isna(row_str):
        return 0

    # Use regex to find the running_total_requests value
    match = re.search(r"'running_total_requests': (\d+)", row_str)
    if match:
        return int(match.group(1))
    return 0


def calculate_rate_of_change(times, values):
    """Calculate rate of change between points, ignoring initial zeros"""
    # Find first non-zero value
    first_nonzero = 0
    for i, v in enumerate(values):
        if v != 0:
            first_nonzero = i
            break

    # Slice arrays to start from first non-zero value
    times = times[first_nonzero:]
    values = values[first_nonzero:]

    # Calculate differences
    time_diff = np.diff(times)
    value_diff = np.diff(values)

    # Calculate rates (handle division by zero) and convert to per minute
    rates = np.where(time_diff != 0, np.abs(value_diff / time_diff) * 60, 0)

    # Apply smoothing using rolling average (increased window size for smoother curve)
    rates = pd.Series(rates).rolling(window=50, min_periods=1).mean()

    # Pad the beginning with None to account for removed zeros
    padding = [None] * first_nonzero
    return np.concatenate((padding, [0], rates))


def create_plot(title, ylabel1, ylabel2):
    """Create a new figure with two y-axes"""
    plt.figure(figsize=(12, 8))
    ax1 = plt.gca()
    ax2 = ax1.twinx()  # Create second y-axis

    # Set labels and title
    ax1.set_xlabel("Time Since Start (minutes)")
    ax1.set_ylabel(ylabel1, color="#1f77b4")
    ax2.set_ylabel(ylabel2, color="#d62728")
    plt.title(title, size=14, pad=20)

    # Style both axes
    for ax in [ax1, ax2]:
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)

    # Function to format x-axis ticks from seconds to minutes
    def format_func(x, _):
        return f"{x/60:.1f}"

    ax1.xaxis.set_major_formatter(plt.FuncFormatter(format_func))

    return ax1, ax2


# Set the style
plt.style.use("seaborn-v0_8-darkgrid")

# Create timestamp for filenames
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Process each metric in a separate figure
for i, csv_file in enumerate(csv_files):
    # Read the CSV file
    df = pd.read_csv(csv_file)
    project_name = df["project"].iloc[0]
    df["time_since_start"] = pd.to_numeric(df["time_since_start"])

    # Redis Queue Size Plot
    ax1, ax2 = create_plot(
        "Redis Queue Size Over Time", "Queue Size", "Rate of Change (items/minute)"
    )

    # Plot raw values
    line1 = ax1.plot(
        df["time_since_start"],
        df["redis_queue_size"],
        label="Queue Size",
        color="#1f77b4",
        marker="o",
        markersize=4,
        linewidth=2,
    )

    # Calculate and plot rate of change
    rate = calculate_rate_of_change(df["time_since_start"], df["redis_queue_size"])
    line2 = ax2.plot(
        df["time_since_start"],
        rate,
        label="Rate of Change",
        color="#d62728",
        linestyle="--",
        linewidth=2,
    )

    # Add legends
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper right")
    plt.tight_layout()
    plt.savefig(
        f"redis_queue_size_with_rate_{timestamp}.png", dpi=300, bbox_inches="tight"
    )

    # Entity Activity Count Plot
    ax1, ax2 = create_plot(
        "Entity Activity Count Over Time",
        "Activity Count",
        "Rate of Change (items/minute)",
    )

    # Plot raw values
    line1 = ax1.plot(
        df["time_since_start"],
        df["postgres_pipeline_entity_activity_count"],
        label="Activity Count",
        color="#1f77b4",
        marker="s",
        markersize=4,
        linewidth=2,
    )

    # Calculate and plot rate of change
    rate = calculate_rate_of_change(
        df["time_since_start"], df["postgres_pipeline_entity_activity_count"]
    )
    line2 = ax2.plot(
        df["time_since_start"],
        rate,
        label="Rate of Change",
        color="#d62728",
        linestyle="--",
        linewidth=2,
    )

    # Add legends
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left")
    plt.tight_layout()
    plt.savefig(
        f"entity_activity_with_rate_{timestamp}.png", dpi=300, bbox_inches="tight"
    )

    # Running Total Requests Plot
    ax1, ax2 = create_plot(
        "Running Total Requests Over Time",
        "Total Requests",
        "Rate of Change (requests/minute)",
    )

    # Extract and plot running total requests
    running_total_requests = df["postgres_pipeline_global_stats_latest_row"].apply(
        extract_running_total_requests
    )
    line1 = ax1.plot(
        df["time_since_start"],
        running_total_requests,
        label="Total Requests",
        color="#1f77b4",
        marker="^",
        markersize=4,
        linewidth=2,
    )

    # Calculate and plot rate of change
    rate = calculate_rate_of_change(df["time_since_start"], running_total_requests)
    line2 = ax2.plot(
        df["time_since_start"],
        rate,
        label="Rate of Change",
        color="#d62728",
        linestyle="--",
        linewidth=2,
    )

    # Add legends
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left")
    plt.tight_layout()
    plt.savefig(
        f"total_requests_with_rate_{timestamp}.png", dpi=300, bbox_inches="tight"
    )

# Show all plots
plt.show()

print(
    f"Plots saved with timestamp {timestamp}:"
    f"\n - redis_queue_size_with_rate_{timestamp}.png"
    f"\n - entity_activity_with_rate_{timestamp}.png"
    f"\n - total_requests_with_rate_{timestamp}.png"
)
