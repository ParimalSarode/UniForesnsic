"""Controlled benchmarking experiment runner executing comparative evaluations across SQLite configurations."""

import csv
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from uniforensic.evaluation.adapters import (
    BaseCarverAdapter,
    Bring2LiteAdapter,
    MLRankerAdapter,
    SqliteDissectAdapter,
    StructuralOnlyAdapter,
)
from uniforensic.evaluation.metrics import (
    BenchmarkMetrics,
    evaluate_system_run,
)
from uniforensic.filter.live_filter import LiveRowFilter
from uniforensic.generator.ground_truth import DatabaseGroundTruth
from uniforensic.generator.scenarios import (
    ForensicDatabaseGenerator,
    ScenarioConfig,
)
from uniforensic.models.pipeline import ForensicMLPipeline


class BenchmarkExperimentRunner:
    """Executes controlled multi-scenario comparative evaluations across recovery systems."""

    def __init__(
        self,
        workspace_dir: Path,
        seed: int = 42,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.generator = ForensicDatabaseGenerator(self.workspace_dir / "generated_dbs")
        self.pipeline = ForensicMLPipeline(seed=seed)
        self.adapters: List[BaseCarverAdapter] = []
        self._is_trained = False

    def setup_models(self) -> Dict[str, Any]:
        """Generate training and calibration databases, and fit ML rankers."""
        train_config = ScenarioConfig("bench_train", seed=self.seed, num_sms_initial=30, num_sms_delete=10)
        calib_config = ScenarioConfig("bench_calib", seed=self.seed + 1, num_sms_initial=25, num_sms_delete=8)

        train_db = self.generator.generate(train_config)
        calib_db = self.generator.generate(calib_config)

        train_summary = self.pipeline.train_and_calibrate([train_db], [calib_db])

        # Initialize adapters
        self.adapters = [
            StructuralOnlyAdapter(),
            MLRankerAdapter(self.pipeline.rf_classifier, "Random Forest (Uncalibrated)"),
            MLRankerAdapter(self.pipeline.calibrated_rf, "Random Forest (Calibrated)"),
            MLRankerAdapter(self.pipeline.gb_classifier, "Gradient Boosted Trees"),
            SqliteDissectAdapter(),
            Bring2LiteAdapter(),
        ]
        self._is_trained = True
        return train_summary

    def run_benchmark_matrix(
        self,
        scenarios: Optional[List[ScenarioConfig]] = None,
        apply_live_filter: bool = True,
    ) -> List[BenchmarkMetrics]:
        """Run all systems across a controlled scenario matrix."""
        if not self._is_trained:
            self.setup_models()

        if scenarios is None:
            scenarios = [
                ScenarioConfig("scenario_default", seed=100, secure_delete=0, auto_vacuum=0),
                ScenarioConfig("scenario_secure_delete", seed=101, secure_delete=1, auto_vacuum=0),
                ScenarioConfig("scenario_auto_vacuum", seed=102, secure_delete=0, auto_vacuum=1),
                ScenarioConfig("scenario_wal_burst", seed=103, journal_mode="WAL", num_sms_initial=35, num_sms_delete=12),
                ScenarioConfig("scenario_corpus_sample", seed=104, num_sms_initial=40, num_sms_delete=15, num_browser_initial=60),
            ]

        all_metrics: List[BenchmarkMetrics] = []

        for sc in scenarios:
            db_path, gt = self.generator.generate(sc)
            live_filter = LiveRowFilter(db_path) if apply_live_filter else None

            for adapter in self.adapters:
                recovered, elapsed = adapter.recover(db_path, live_filter=live_filter)
                metrics = evaluate_system_run(
                    system_name=adapter.name,
                    scenario_name=sc.name,
                    recovered_records=recovered,
                    ground_truth=gt,
                    runtime_seconds=elapsed,
                )
                all_metrics.append(metrics)

        return all_metrics

    def export_results(
        self,
        metrics: List[BenchmarkMetrics],
        json_path: Path,
        csv_path: Path,
    ) -> None:
        """Export metrics to JSON and CSV formats."""
        records = [m.to_dict() for m in metrics]

        # JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        # CSV
        df = pd.DataFrame(records)
        df.to_csv(csv_path, index=False)

    @staticmethod
    def aggregate_by_system(metrics: List[BenchmarkMetrics]) -> pd.DataFrame:
        """Compute aggregated summary statistics per recovery system."""
        df = pd.DataFrame([m.to_dict() for m in metrics])
        agg = df.groupby("system_name").agg({
            "raw_precision": "mean",
            "filtered_precision": "mean",
            "recall": "mean",
            "f1_score": "mean",
            "live_fp_rate": "mean",
            "ghost_fp_rate": "mean",
            "brier_score": "mean",
            "expected_calibration_error": "mean",
            "runtime_seconds": "mean",
        }).reset_index()

        return agg.round(4)
