"""Unit and integration tests for synthetic database generator and ground truth."""

import sqlite3
from pathlib import Path
import pytest

from uniforensic.generator.ground_truth import (
    DatabaseGroundTruth,
    RecordStatus,
    compute_file_sha256,
)
from uniforensic.generator.schemas import (
    SMS_SCHEMA,
    SyntheticRecordFactory,
)
from uniforensic.generator.scenarios import (
    ForensicDatabaseGenerator,
    ScenarioConfig,
)
import random


def test_synthetic_record_factory():
    rng = random.Random(42)
    factory = SyntheticRecordFactory(rng)
    sms = factory.generate_sms(1)
    assert sms["id"] == 1
    assert "sender" in sms
    assert "recipient" in sms
    assert "body" in sms
    assert "timestamp" in sms

    call = factory.generate_call(2)
    assert call["id"] == 2
    assert "phone_number" in call
    assert call["call_type"] in (1, 2, 3, 4)

    hist = factory.generate_browser_history(3)
    assert hist["id"] == 3
    assert hist["url"].startswith("http")


def test_database_generation_and_ground_truth(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="test_db",
        seed=123,
        num_sms_initial=20,
        num_sms_delete=5,
        num_sms_update=2,
        num_calls_initial=15,
        num_calls_delete=3,
        num_calls_update=1,
        num_browser_initial=25,
        num_browser_delete=5,
        num_browser_update=2,
        freelist_burst_count=20,
        distractor_count=3,
    )
    db_path, gt = gen.generate(cfg)

    # 1. Evidence file exists and hash is computed
    assert db_path.exists()
    assert gt.db_sha256 == compute_file_sha256(db_path)

    # 2. SQLite can query live records
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM messages")
    sms_live_count = cur.fetchone()[0]
    # initial - deleted = 20 - 5 = 15
    assert sms_live_count == 15

    # 3. Ground truth contains both live and deleted records
    live_records = gt.get_live_records("messages")
    deleted_records = gt.get_deleted_records("messages")
    assert len(live_records) == 15
    assert len(deleted_records) >= 5

    # 4. JSON serialization roundtrip
    json_path = tmp_path / "test_db_ground_truth.json"
    assert json_path.exists()
    loaded_gt = DatabaseGroundTruth.load_json(json_path)
    assert loaded_gt.database_id == "test_db"
    assert loaded_gt.db_sha256 == gt.db_sha256
    assert len(loaded_gt.records) == len(gt.records)

    conn.close()


def test_secure_delete_marks_overwritten(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="secure_db",
        seed=999,
        secure_delete=1,  # ON
        num_sms_initial=10,
        num_sms_delete=4,
        freelist_burst_count=10,
    )
    db_path, gt = gen.generate(cfg)
    deleted_sms = [r for r in gt.records if r.table_name == "messages" and r.scenario == "freeblock_scattered_delete"]
    assert len(deleted_sms) == 4
    # With secure_delete=1, deleted records are marked DELETED_OVERWRITTEN
    assert all(r.status == RecordStatus.DELETED_OVERWRITTEN for r in deleted_sms)
