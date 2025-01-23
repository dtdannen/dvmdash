import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Dictionary of CSV files with labels
csv_files = {
    "n=1": "experiments/data/run_2025_Jan_21_at_23_58_26/yellow-mouse_1BP_2025_Jan_21_at_23_58_26_metrics.csv",
    "n=2": "experiments/data/run_2025_Jan_21_at_23_59_31/purple-duck_2BP_2025_Jan_21_at_23_59_31_metrics.csv",
    "n=3": "experiments/data/run_2025_Jan_21_at_22_34_56/gray-goat_3BP_2025_Jan_21_at_22_34_56_metrics.csv",
    "n=4": "experiments/data/run_2025_Jan_22_at_00_06_54/pink-sheep_4BP_2025_Jan_22_at_00_06_54_metrics.csv",
    "n=5": "experiments/data/run_2025_Jan_22_at_00_49_34/brown-sheep_5BP_2025_Jan_22_at_00_49_34_metrics.csv",
    "n=6": "experiments/data/run_2025_Jan_21_at_23_27_05/purple-bird_6BP_2025_Jan_21_at_23_27_05_metrics.csv",
}

# Color scheme for different BP configurations
bp_colors = {
    "n=1": "#1f77b4",  # Blue
    "n=2": "#9467bd",  # Purple
    "n=3": "#ff7f0e",  # Orange
    "n=4": "#e377c2",  # Pink
    "n=5": "#8c564b",  # Brown
    "n=6": "#2ca02c",  # Green
}

# Styles for raw values vs rates
metric_styles = {
    "raw": {"linestyle": "-", "marker": "o", "markersize": 4},
    "rate": {"linestyle": "--", "marker": None},
}


def calculate_rate_of_change(times, values):
    """Calculate rate of change between points, ignoring initial zeros"""
    first_nonzero = 0
    for i, v in enumerate(values):
        if v != 0:
            first_nonzero = i
            break

    times = times[first_nonzero:]
    values = values[first_nonzero:]

    time_diff = np.diff(times)
    value_diff = np.diff(values)
    rates = np.where(time_diff != 0, np.abs(value_diff / time_diff) * 60, 0)
    rates = pd.Series(rates).rolling(window=50, min_periods=1).mean()

    padding = [None] * first_nonzero
    return np.concatenate((padding, [0], rates))


def create_plot(title, ylabel1, ylabel2):
    """Create a new figure with two y-axes"""
    plt.figure(figsize=(12, 8))
    ax1 = plt.gca()
    ax2 = ax1.twinx()

    # Increase font size for title
    plt.title(title, size=14, pad=20)

    # Increase font size for x-axis label and add padding
    ax1.set_xlabel(
        "Time Since Start (minutes)", size=12, labelpad=10  # Larger font
    )  # Add space between label and numbers

    # Increase font size for y-axis labels and add padding
    ax1.set_ylabel(
        ylabel1, color="black", size=12, labelpad=10  # Larger font
    )  # Add space between label and numbers

    ax2.set_ylabel(
        ylabel2, color="black", size=12, labelpad=10  # Larger font
    )  # Add space between label and numbers

    # Optionally increase tick label sizes
    ax1.tick_params(axis="both", which="major", labelsize=10)
    ax2.tick_params(axis="both", which="major", labelsize=10)

    for ax in [ax1, ax2]:
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.spines["top"].set_visible(False)

    def format_func(x, _):
        return f"{x/60:.1f}"

    def format_k(x, _):
        if x >= 1000000:
            return f"{x/1000000:.1f}M"
        return f"{x/1000:.0f}k"  # This will show 100k, 200k, etc.

    ax2.yaxis.set_major_formatter(plt.FuncFormatter(format_k))
    ax1.xaxis.set_major_formatter(plt.FuncFormatter(format_func))

    return ax1, ax2


# Set the style
plt.style.use("seaborn-v0_8-darkgrid")

# Create timestamp for filenames
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Create figure with shared x-axis subplots, but allow top plot to show x-axis
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), height_ratios=[1, 1])

lines1, lines2 = [], []

# Process data for both plots
for idx, (label, csv_file) in enumerate(csv_files.items()):
    print(f"Processing Label {label} with color {bp_colors[label]}")
    df = pd.read_csv(csv_file)
    df["time_since_start"] = pd.to_numeric(df["time_since_start"])

    # Calculate alpha value
    alpha = 1.0

    # Plot queue size (top subplot) - divide by 1e6 for millions
    line1 = ax1.plot(
        df["time_since_start"],
        df["postgres_events"] / 1e6,  # Convert to millions
        label=f"Events Processed with {label} ",
        color=bp_colors[label],
        **metric_styles["raw"],
        linewidth=2,
        alpha=alpha,
    )
    lines1.extend(line1)

    # Calculate and plot rate (bottom subplot)
    rate = calculate_rate_of_change(df["time_since_start"], df["redis_queue_size"])
    line2 = ax2.plot(
        df["time_since_start"],
        rate,
        label=f"Processing Rate with {label}",
        color=bp_colors[label],
        **metric_styles["rate"],
        linewidth=2,
        alpha=alpha,
    )
    lines2.extend(line2)

# Customize plots
for ax in [ax1, ax2]:
    ax.tick_params(axis="both", which="major", labelsize=10)
    ax.grid(True, linestyle="--", alpha=0.7)
    ax.spines["top"].set_visible(False)


# Format x-axis (only needed once due to sharex=True)
def format_func(x, _):
    return f"{x/60:.1f}"


ax1.xaxis.set_major_formatter(plt.FuncFormatter(format_func))
ax2.xaxis.set_major_formatter(plt.FuncFormatter(format_func))


# Format rate y-axis to show 500k intervals
def format_500k(x, _):
    return f"{x/1000:.0f}k" if x < 1000000 else f"{x/1000000:.1f}M"


ax2.yaxis.set_major_formatter(plt.FuncFormatter(format_500k))

# Set labels and titles
ax1.set_ylabel("DVM Events (millions)", size=12, labelpad=10)
ax2.set_ylabel("Rate of Change (items/minute)", size=12, labelpad=10)
ax1.set_xlabel("Time Since Start (minutes)", size=12, labelpad=10)
ax2.set_xlabel("Time Since Start (minutes)", size=12, labelpad=10)

ax1.set_title("DVM Events Processed Over Time", size=14, pad=20)
ax2.set_title("Processing Speed (DVM events per minute)", size=14, pad=20)

# Add legends
ax1.legend(
    lines1,
    [l.get_label() for l in lines1],
    loc="lower right",
    bbox_to_anchor=(1, 0),
    ncol=1,
    frameon=True,
    framealpha=0.8,
)

ax2.legend(
    lines2,
    [l.get_label() for l in lines2],
    loc="upper right",
    bbox_to_anchor=(1, 1),
    ncol=1,
    frameon=True,
    framealpha=0.8,
)

# Adjust spacing between subplots
plt.subplots_adjust(hspace=0.5)  # Increase this value for more space

# Save figure
plt.savefig(f"redis_queue_analysis_{timestamp}.png", dpi=300, bbox_inches="tight")
## SECOND GRAPH

# Entity Activity Count Plot
ax1, ax2 = create_plot(
    "Entity Activity Count Over Time by Number of Batch Processors",
    "Activity Count",
    "Rate of Change (items/minute)",
)

lines1, lines2 = [], []
labels = []

for idx, (label, csv_file) in enumerate(csv_files.items()):
    print(f"Processing Label {label} with color {bp_colors[label]}")
    df = pd.read_csv(csv_file)
    df["time_since_start"] = pd.to_numeric(df["time_since_start"])

    # Calculate alpha value
    alpha = 1.0 - (idx * 0.15)

    # Plot raw values
    line1 = ax1.plot(
        df["time_since_start"],
        df["postgres_pipeline_entity_activity_count"],
        label=f"{label} Activity Count",
        color=bp_colors[label],
        **metric_styles["raw"],
        linewidth=2,
        alpha=alpha,
    )

    # Plot rate
    rate = calculate_rate_of_change(
        df["time_since_start"], df["postgres_pipeline_entity_activity_count"]
    )
    line2 = ax2.plot(
        df["time_since_start"],
        rate,
        label=f"{label} Rate",
        color=bp_colors[label],
        **metric_styles["rate"],
        linewidth=2,
        alpha=alpha,
    )

    lines1.extend(line1)
    lines2.extend(line2)
    labels += [f"{label} (Activity Count)", f"{label} (Rate)"]

# Add combined legend
all_lines = lines1 + lines2
all_labels = [l.get_label() for l in all_lines]

# Create single legend using plt.legend instead of ax1.legend
plt.legend(
    all_lines,
    all_labels,
    loc="upper right",  # or 'upper left' for the second plot
    bbox_to_anchor=(1, 1),
    ncol=1,
    frameon=True,
    framealpha=0.8,
)
plt.tight_layout()
plt.savefig(f"entity_activity_comparison_{timestamp}.png", dpi=300, bbox_inches="tight")

# Show all plots
plt.show()

print(
    f"Plots saved with timestamp {timestamp}:"
    f"\n - redis_queue_size_comparison_{timestamp}.png"
    f"\n - entity_activity_comparison_{timestamp}.png"
)
