"""Plotting utilities for reliability diagrams, calibration curves, and benchmark visualizations."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import matplotlib
matplotlib.use("Agg")  # Headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from uniforensic.evaluation.metrics import BenchmarkMetrics


def plot_reliability_diagram(
    uncalibrated_metrics: Dict[str, Any],
    calibrated_metrics: Dict[str, Any],
    output_path: Path,
) -> None:
    """
    Plot comparative reliability diagram (ECE & calibration curves)
    comparing uncalibrated vs calibrated probabilities.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=300)

    # 1. Uncalibrated curve
    u_pred = uncalibrated_metrics.get("prob_pred", [])
    u_true = uncalibrated_metrics.get("prob_true", [])
    u_ece = uncalibrated_metrics.get("expected_calibration_error", 0.0)
    u_brier = uncalibrated_metrics.get("brier_score", 0.0)

    ax1.plot([0, 1], [0, 1], "k--", label="Perfect Calibration (y = x)")
    if u_pred and u_true:
        ax1.plot(u_pred, u_true, "s-", color="#d9534f", label=f"Uncalibrated RF (ECE={u_ece:.3f}, Brier={u_brier:.3f})")
    ax1.set_title("Uncalibrated Random Forest Reliability", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Mean Predicted Confidence", fontsize=10)
    ax1.set_ylabel("Observed Fraction of Positives", fontsize=10)
    ax1.set_xlim([0, 1])
    ax1.set_ylim([0, 1])
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="lower right", fontsize=9)

    # 2. Calibrated curve
    c_pred = calibrated_metrics.get("prob_pred", [])
    c_true = calibrated_metrics.get("prob_true", [])
    c_ece = calibrated_metrics.get("expected_calibration_error", 0.0)
    c_brier = calibrated_metrics.get("brier_score", 0.0)

    ax2.plot([0, 1], [0, 1], "k--", label="Perfect Calibration (y = x)")
    if c_pred and c_true:
        ax2.plot(c_pred, c_true, "o-", color="#2e6da4", label=f"Calibrated RF (ECE={c_ece:.3f}, Brier={c_brier:.3f})")
    ax2.set_title("Calibrated Random Forest (Isotonic)", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Mean Predicted Confidence", fontsize=10)
    ax2.set_ylabel("Observed Fraction of Positives", fontsize=10)
    ax2.set_xlim([0, 1])
    ax2.set_ylim([0, 1])
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="lower right", fontsize=9)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path)
    plt.close(fig)


def plot_system_comparison(
    agg_df: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    Plot comparative bar chart comparing Precision, Recall, F1,
    and Live-Row FP Rate across all benchmarked systems.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), dpi=300)

    systems = agg_df["system_name"].tolist()
    y_pos = np.arange(len(systems))
    bar_width = 0.25

    # 1. Precision, Recall, F1
    f1s = agg_df["f1_score"].tolist()
    precs = agg_df["filtered_precision"].tolist()
    recs = agg_df["recall"].tolist()

    ax1.barh(y_pos - bar_width, precs, height=bar_width, label="Filtered Precision", color="#5cb85c", alpha=0.85)
    ax1.barh(y_pos, recs, height=bar_width, label="Recall", color="#337ab7", alpha=0.85)
    ax1.barh(y_pos + bar_width, f1s, height=bar_width, label="F1 Score", color="#f0ad4e", alpha=0.85)

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(systems, fontsize=9)
    ax1.set_xlim([0, 1.05])
    ax1.set_xlabel("Metric Score [0.0 - 1.0]", fontsize=10)
    ax1.set_title("Recovery Performance Comparison (Higher is Better)", fontsize=11, fontweight="bold")
    ax1.legend(loc="lower right", fontsize=9)
    ax1.grid(True, axis="x", linestyle=":", alpha=0.6)

    # 2. Live-Row FP Rate vs Ghost FP Rate
    live_fps = agg_df["live_fp_rate"].tolist()
    ghost_fps = agg_df["ghost_fp_rate"].tolist()

    ax2.barh(y_pos - (bar_width / 2), live_fps, height=bar_width, label="Live-Row FP Rate", color="#d9534f", alpha=0.85)
    ax2.barh(y_pos + (bar_width / 2), ghost_fps, height=bar_width, label="Ghost/Noise FP Rate", color="#777777", alpha=0.85)

    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(systems, fontsize=9)
    ax2.set_xlim([0, max(0.5, max(live_fps + ghost_fps) * 1.2 if (live_fps + ghost_fps) else 0.5)])
    ax2.set_xlabel("False Positive Fraction", fontsize=10)
    ax2.set_title("False Positive Distribution (Lower is Better)", fontsize=11, fontweight="bold")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, axis="x", linestyle=":", alpha=0.6)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path)
    plt.close(fig)


def plot_scenario_breakdown(
    metrics: List[BenchmarkMetrics],
    output_path: Path,
) -> None:
    """Plot F1 score across scenarios for each system."""
    df = pd.DataFrame([m.to_dict() for m in metrics])
    pivot_f1 = df.pivot(index="scenario_name", columns="system_name", values="f1_score")

    fig, ax = plt.subplots(figsize=(12, 6), dpi=300)
    pivot_f1.plot(kind="bar", ax=ax, width=0.8, colormap="tab10")

    ax.set_title("F1 Score Across Diverse SQLite Forensic Scenarios", fontsize=12, fontweight="bold")
    ax.set_xlabel("Evaluation Scenario", fontsize=10)
    ax.set_ylabel("F1 Score", fontsize=10)
    ax.set_ylim([0, 1.05])
    plt.xticks(rotation=20, ha="right", fontsize=9)
    ax.legend(title="Recovery System", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
    ax.grid(True, axis="y", linestyle=":", alpha=0.6)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path)
    plt.close(fig)
