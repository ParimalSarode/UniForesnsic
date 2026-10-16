"""Unit and integration tests for comparative forensics evaluation suite."""

from pathlib import Path
import pytest

from uniforensic.evaluation.adapters import (
    Bring2LiteAdapter,
    SqliteDissectAdapter,
    StructuralOnlyAdapter,
)
from uniforensic.evaluation.benchmark_runner import BenchmarkExperimentRunner
from uniforensic.evaluation.metrics import evaluate_system_run
from uniforensic.filter.live_filter import LiveRowFilter
from uniforensic.generator.scenarios import (
    ForensicDatabaseGenerator,
    ScenarioConfig,
)


def test_sqlite_dissect_and_structural_adapters(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    config = ScenarioConfig("adapter_test", seed=77, num_sms_initial=20, num_sms_delete=6)
    db_path, gt = gen.generate(config)

    live_filter = LiveRowFilter(db_path)

    # 1. Structural-Only Adapter
    struct_adapter = StructuralOnlyAdapter()
    struct_rec, struct_time = struct_adapter.recover(db_path, live_filter=live_filter)
    assert len(struct_rec) > 0
    assert struct_time > 0.0

    struct_metrics = evaluate_system_run(
        system_name=struct_adapter.name,
        scenario_name=config.name,
        recovered_records=struct_rec,
        ground_truth=gt,
        runtime_seconds=struct_time,
    )
    assert struct_metrics.total_recovered > 0
    assert 0.0 <= struct_metrics.filtered_precision <= 1.0
    assert 0.0 <= struct_metrics.recall <= 1.0

    # 2. sqlite_dissect Adapter
    dissect_adapter = SqliteDissectAdapter()
    dissect_rec, dissect_time = dissect_adapter.recover(db_path, live_filter=live_filter)
    assert dissect_time > 0.0
    # sqlite_dissect should carve cells without crashing
    dissect_metrics = evaluate_system_run(
        system_name=dissect_adapter.name,
        scenario_name=config.name,
        recovered_records=dissect_rec,
        ground_truth=gt,
        runtime_seconds=dissect_time,
    )
    assert dissect_metrics.runtime_seconds > 0.0

    # 3. bring2lite Adapter
    b2l_adapter = Bring2LiteAdapter()
    b2l_rec, b2l_time = b2l_adapter.recover(db_path, live_filter=live_filter)
    assert b2l_time > 0.0
    b2l_metrics = evaluate_system_run(
        system_name=b2l_adapter.name,
        scenario_name=config.name,
        recovered_records=b2l_rec,
        ground_truth=gt,
        runtime_seconds=b2l_time,
    )
    assert b2l_metrics.runtime_seconds > 0.0


def test_benchmark_runner_pipeline(tmp_path: Path):
    runner = BenchmarkExperimentRunner(tmp_path, seed=42)
    train_summary = runner.setup_models()
    assert train_summary["n_train_samples"] > 0
    assert len(runner.adapters) == 6

    # Run on a compact 2-scenario matrix for swift verification
    test_scenarios = [
        ScenarioConfig("mini_default", seed=10, num_sms_initial=15, num_sms_delete=5),
        ScenarioConfig("mini_secure", seed=11, secure_delete=1, num_sms_initial=15, num_sms_delete=5),
    ]

    metrics = runner.run_benchmark_matrix(test_scenarios, apply_live_filter=True)
    # 2 scenarios * 6 adapters = 12 metric results
    assert len(metrics) == 12

    # Verify export
    json_p = tmp_path / "results.json"
    csv_p = tmp_path / "results.csv"
    runner.export_results(metrics, json_p, csv_p)

    assert json_p.exists() and json_p.stat().st_size > 0
    assert csv_p.exists() and csv_p.stat().st_size > 0

    agg_df = runner.aggregate_by_system(metrics)
    assert len(agg_df) == 6
    assert "filtered_precision" in agg_df.columns
    assert "f1_score" in agg_df.columns
