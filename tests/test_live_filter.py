"""Unit and integration tests for LiveRowFilter and segregated metrics."""

from pathlib import Path
import pytest

from uniforensic.carver.btree_carver import BTreeCarver
from uniforensic.carver.candidate import RegionType
from uniforensic.filter.live_filter import (
    CollisionType,
    LiveRowFilter,
    compute_segregated_metrics,
)
from uniforensic.generator.scenarios import ForensicDatabaseGenerator, ScenarioConfig


def test_live_filter_indexing_and_detection(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    config = ScenarioConfig("live_test", seed=101, num_sms_initial=15, num_sms_delete=5)
    db_path, gt = gen.generate(config)

    filter_engine = LiveRowFilter(db_path)
    assert "messages" in filter_engine.live_rows_by_table
    assert len(filter_engine.live_rows_by_table["messages"]) == 10  # 15 initial - 5 deleted = 10 live

    # Carve all candidates including live cells
    carver = BTreeCarver(db_path)
    all_cands = carver.carve_all(include_live=True)

    # Check collision on live cell candidates
    live_cands = [c for c in all_cands if c.region_type == RegionType.LIVE_CELL]
    assert len(live_cands) > 0

    detected_live_collisions = 0
    for cand in live_cands:
        res = filter_engine.check_collision(cand)
        if res.is_live_collision:
            detected_live_collisions += 1
            assert res.collision_type in (
                CollisionType.PRIMARY_KEY,
                CollisionType.EXACT_TUPLE,
                CollisionType.PARTIAL_OVERLAP,
            )

    # All or nearly all live cells should be detected as live collisions
    assert detected_live_collisions >= len(live_cands) * 0.9


def test_segregated_metrics_computation(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    config = ScenarioConfig("seg_test", seed=202, num_sms_initial=20, num_sms_delete=6)
    db_path, gt = gen.generate(config)

    carver = BTreeCarver(db_path)
    all_cands = carver.carve_all(include_live=True)
    filter_engine = LiveRowFilter(db_path)

    # Simulate a naive model that predicts ALL candidates as recovered deleted records
    naive_preds = [1] * len(all_cands)
    metrics_naive = compute_segregated_metrics(all_cands, naive_preds, gt, live_filter=filter_engine)

    assert metrics_naive.total_candidates == len(all_cands)
    assert metrics_naive.false_positives_live > 0  # Naive carver suffers heavy live-row false positives
    assert metrics_naive.true_positives > 0

    # Filtered precision should be strictly greater than raw precision because live collisions are removed
    assert metrics_naive.filtered_precision >= metrics_naive.raw_precision
    assert metrics_naive.live_fp_rate > 0.0

    # Now filter out live candidates before predicting
    filtered_cands, filter_res = filter_engine.filter_candidates(all_cands, filter_live=True)
    filtered_preds = [1] * len(filtered_cands)
    metrics_filtered = compute_segregated_metrics(filtered_cands, filtered_preds, gt, live_filter=filter_engine)

    # After live-row filtering, false_positives_live should be drastically reduced or zero
    assert metrics_filtered.false_positives_live == 0
