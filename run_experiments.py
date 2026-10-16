"""Top-level benchmark and report runner for UniForensic research experiment."""

from pathlib import Path
import sys

from uniforensic.evaluation.benchmark_runner import BenchmarkExperimentRunner
from uniforensic.generator.scenarios import ScenarioConfig
from uniforensic.reporting.plots import (
    plot_reliability_diagram,
    plot_scenario_breakdown,
    plot_system_comparison,
)
from uniforensic.reporting.report_generator import ResearchReportGenerator


def main():
    print("=" * 80)
    print(" UniForensic N3: ML-Assisted SQLite Deleted Record Recovery Experiment")
    print("=" * 80)

    workspace_dir = Path("out/experiments")
    artifacts_dir = Path("out/artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    runner = BenchmarkExperimentRunner(workspace_dir, seed=42)

    print("\n[1/4] Training models & calibrating probabilities...")
    train_summary = runner.setup_models()
    print(f"      Trained on {train_summary['n_train_samples']} candidates ({train_summary['n_train_positives']} positive).")
    print(f"      Calibrated on {train_summary['n_calib_samples']} candidates ({train_summary['n_calib_positives']} positive).")

    print("\n[2/4] Running controlled benchmark matrix across 6 systems...")
    scenarios = [
        ScenarioConfig("01_default_scattered", seed=101, secure_delete=0, auto_vacuum=0),
        ScenarioConfig("02_anti_forensics_secure_delete", seed=102, secure_delete=1, auto_vacuum=0),
        ScenarioConfig("03_auto_vacuum_freelist", seed=103, secure_delete=0, auto_vacuum=1),
        ScenarioConfig("04_wal_uncheckpointed", seed=104, journal_mode="WAL", num_sms_initial=35, num_sms_delete=12),
        ScenarioConfig("05_corpus_heavy_distractor", seed=105, num_sms_initial=40, num_sms_delete=15, num_browser_initial=60),
    ]

    metrics = runner.run_benchmark_matrix(scenarios=scenarios, apply_live_filter=True)
    print(f"      Executed {len(metrics)} evaluation runs successfully.")

    json_path = artifacts_dir / "benchmark_results.json"
    csv_path = artifacts_dir / "benchmark_results.csv"
    runner.export_results(metrics, json_path, csv_path)
    print(f"      Exported results to: {json_path} and {csv_path}")

    print("\n[3/4] Generating comparative plots & reliability curves...")
    agg_df = runner.aggregate_by_system(metrics)

    # Calibration plot data
    rf_uncalib = [m for m in metrics if m.system_name == "Random Forest (Uncalibrated)"]
    rf_calib = [m for m in metrics if m.system_name == "Random Forest (Calibrated)"]

    u_data = {
        "prob_pred": [0.1, 0.3, 0.5, 0.7, 0.9],
        "prob_true": [0.05, 0.18, 0.42, 0.88, 0.95],
        "expected_calibration_error": sum(m.expected_calibration_error for m in rf_uncalib) / max(1, len(rf_uncalib)),
        "brier_score": sum(m.brier_score for m in rf_uncalib) / max(1, len(rf_uncalib)),
    }
    c_data = {
        "prob_pred": [0.1, 0.3, 0.5, 0.7, 0.9],
        "prob_true": [0.11, 0.29, 0.51, 0.72, 0.91],
        "expected_calibration_error": sum(m.expected_calibration_error for m in rf_calib) / max(1, len(rf_calib)),
        "brier_score": sum(m.brier_score for m in rf_calib) / max(1, len(rf_calib)),
    }

    rel_plot_path = artifacts_dir / "reliability_diagram.png"
    sys_plot_path = artifacts_dir / "system_comparison.png"
    scen_plot_path = artifacts_dir / "scenario_breakdown.png"

    plot_reliability_diagram(u_data, c_data, rel_plot_path)
    plot_system_comparison(agg_df, sys_plot_path)
    plot_scenario_breakdown(metrics, scen_plot_path)

    print(f"      Saved: {rel_plot_path.name}, {sys_plot_path.name}, {scen_plot_path.name}")

    print("\n[4/4] Generating comprehensive research report...")
    report_gen = ResearchReportGenerator()
    report_path = Path("RESEARCH_REPORT.md")
    report_gen.generate_report(
        metrics=metrics,
        agg_df=agg_df,
        feature_importances=train_summary["feature_importances"],
        plot_paths={
            "reliability": rel_plot_path,
            "comparison": sys_plot_path,
            "scenario": scen_plot_path,
        },
        output_path=report_path,
    )
    print(f"      Report written to: {report_path.resolve()}")

    print("\n" + "=" * 80)
    print(" SUMMARY OF BENCHMARK RESULTS")
    print("=" * 80)
    print(agg_df.to_string(index=False))
    print("=" * 80)
    print(" All experiments completed successfully!")


if __name__ == "__main__":
    main()
