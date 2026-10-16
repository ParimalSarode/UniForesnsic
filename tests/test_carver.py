"""Unit and integration tests for SQLite structural candidate carvers."""

from pathlib import Path
import pytest

from uniforensic.carver.btree_carver import BTreeCarver
from uniforensic.carver.candidate import RegionType
from uniforensic.carver.wal_carver import WALCarver
from uniforensic.generator.scenarios import ForensicDatabaseGenerator, ScenarioConfig


def test_btree_carver_extracts_deleted_and_live(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="carver_test_db",
        seed=1001,
        secure_delete=0,
        auto_vacuum=0,
        num_sms_initial=25,
        num_sms_delete=8,
        freelist_burst_count=15,
    )
    db_path, gt = gen.generate(cfg)

    carver = BTreeCarver(db_path)
    candidates = carver.carve_all(include_live=True)

    assert len(candidates) > 0

    # Categorize by region type
    live_cands = [c for c in candidates if c.region_type == RegionType.LIVE_CELL]
    fb_cands = [c for c in candidates if c.region_type == RegionType.FREEBLOCK]
    unalloc_cands = [c for c in candidates if c.region_type == RegionType.UNALLOCATED_SPACE]
    freelist_cands = [c for c in candidates if c.region_type == RegionType.FREELIST_PAGE]

    assert len(live_cands) >= 17  # 25 - 8 = 17 live SMS
    assert len(fb_cands) > 0       # 8 deleted SMS created freeblocks
    assert all(c.is_structurally_valid for c in live_cands)
    assert all(c.byte_offset >= 0 for c in candidates)
    assert all(c.matched_table is not None for c in live_cands)


def test_wal_carver_extracts_frames(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="wal_carver_db",
        seed=1002,
        journal_mode="WAL",
        wal_checkpoint_mode="PASSIVE",
        num_sms_initial=30,
        num_sms_delete=10,
    )
    db_path, gt = gen.generate(cfg)
    wal_path = tmp_path / "wal_carver_db.sqlite-wal"

    if wal_path.exists() and wal_path.stat().st_size > 32:
        wal_carver = WALCarver(wal_path)
        wal_cands = wal_carver.carve()
        assert len(wal_cands) > 0
        assert all(c.region_type == RegionType.WAL_FRAME for c in wal_cands)
        assert all(c.byte_offset > 0 for c in wal_cands)


def test_secure_delete_produces_no_valid_freeblock_candidates(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="secure_delete_carver_db",
        seed=1003,
        secure_delete=1,  # ON: SQLite zeros deleted cells
        auto_vacuum=0,
        num_sms_initial=15,
        num_sms_delete=6,
        freelist_burst_count=0,
    )
    db_path, gt = gen.generate(cfg)

    carver = BTreeCarver(db_path)
    candidates = carver.carve_all(include_live=False)

    # In secure_delete=1, freeblocks are zeroed out (0x00), so no valid records can be carved
    fb_cands = [c for c in candidates if c.region_type == RegionType.FREEBLOCK]
    assert len(fb_cands) == 0
