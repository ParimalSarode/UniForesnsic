"""Forensic scenario database generator with realistic SQLite operations and ground truth tracking."""

from dataclasses import dataclass, field
from pathlib import Path
import random
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from uniforensic.generator.ground_truth import (
    DatabaseGroundTruth,
    GroundTruthRecord,
    RecordStatus,
    compute_file_sha256,
)
from uniforensic.generator.schemas import (
    SCHEMAS,
    SyntheticRecordFactory,
    TableSchema,
)


@dataclass
class ScenarioConfig:
    name: str
    seed: int
    secure_delete: int = 0         # 0=OFF, 1=ON, 2=FAST
    auto_vacuum: int = 0           # 0=NONE, 1=FULL, 2=INCREMENTAL
    journal_mode: str = "DELETE"   # DELETE, WAL, TRUNCATE, MEMORY
    page_size: int = 4096
    num_sms_initial: int = 40
    num_sms_delete: int = 15
    num_sms_update: int = 5
    num_calls_initial: int = 35
    num_calls_delete: int = 12
    num_calls_update: int = 4
    num_browser_initial: int = 50
    num_browser_delete: int = 20
    num_browser_update: int = 6
    freelist_burst_count: int = 120  # Number of rows to delete contiguously to trigger freelist leaf pages
    wal_checkpoint_mode: Optional[str] = None  # None, "PASSIVE", "FULL", "RESTART", "TRUNCATE"
    distractor_count: int = 10


class ForensicDatabaseGenerator:
    """Generates SQLite databases with controlled deletion scenarios and independent ground truth."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, config: ScenarioConfig) -> Tuple[Path, DatabaseGroundTruth]:
        rng = random.Random(config.seed)
        factory = SyntheticRecordFactory(rng, base_timestamp=1700000000 + (config.seed * 1000))
        db_filename = f"{config.name}.sqlite"
        db_path = self.output_dir / db_filename
        if db_path.exists():
            db_path.unlink()
        wal_path = self.output_dir / f"{db_filename}-wal"
        if wal_path.exists():
            wal_path.unlink()
        shm_path = self.output_dir / f"{db_filename}-shm"
        if shm_path.exists():
            shm_path.unlink()

        gt = DatabaseGroundTruth(
            database_id=config.name,
            db_filename=db_filename,
            db_sha256="",
            seed=config.seed,
            sqlite_config={
                "secure_delete": config.secure_delete,
                "auto_vacuum": config.auto_vacuum,
                "journal_mode": config.journal_mode,
                "page_size": config.page_size,
            }
        )

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Step 1: Configure database pragmas
        cur.execute(f"PRAGMA page_size = {config.page_size};")
        cur.execute(f"PRAGMA auto_vacuum = {config.auto_vacuum};")
        cur.execute(f"PRAGMA secure_delete = {config.secure_delete};")
        cur.execute(f"PRAGMA journal_mode = {config.journal_mode};")

        # Step 2: Create tables
        for schema in SCHEMAS.values():
            cur.execute(schema.create_sql)
        conn.commit()

        # Helper to insert and track
        def insert_records(table_name: str, count: int, start_id: int) -> List[Dict[str, Any]]:
            cols = SCHEMAS[table_name].column_names()
            insert_cols = [c for c in cols if c != "id"]
            placeholders = ", ".join(["?"] * len(insert_cols))
            sql = f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({placeholders})"
            inserted = []
            for i in range(count):
                rec = factory.generate_record(table_name, start_id + i)
                vals = [rec[c] for c in insert_cols]
                cur.execute(sql, vals)
                rec["id"] = cur.lastrowid
                inserted.append(rec)
            return inserted

        # Step 3: Populate tables
        sms_records = insert_records("messages", config.num_sms_initial, 1)
        calls_records = insert_records("call_history", config.num_calls_initial, 1)
        browser_records = insert_records("browser_history", config.num_browser_initial, 1)
        conn.commit()

        # Step 4: Perform Freelist Burst (insert large batch into a temporary table or messages then delete all to create freelist pages)
        # We insert a burst of browser records into a dedicated table or browser_history to fill multiple pages, then delete them
        burst_records = insert_records("browser_history", config.freelist_burst_count, 1000)
        conn.commit()

        # Step 5: Deletions
        # If secure_delete is 1, deleted records are zeroed out by SQLite.
        # Otherwise, they remain in freeblocks/freelist pages.
        expected_status = (
            RecordStatus.DELETED_OVERWRITTEN if config.secure_delete == 1
            else RecordStatus.DELETED_RECOVERABLE
        )

        # A: Delete scattered SMS records (creates freeblocks inside leaf pages)
        rng.shuffle(sms_records)
        sms_to_delete = sms_records[:config.num_sms_delete]
        sms_remaining = sms_records[config.num_sms_delete:]
        for r in sms_to_delete:
            cur.execute("DELETE FROM messages WHERE id = ?", (r["id"],))
            gt.add_record(
                record_id=r["id"],
                table_name="messages",
                values=r,
                status=expected_status,
                scenario="freeblock_scattered_delete",
                notes="Single cell deleted, converted to B-tree freeblock"
            )
        conn.commit()

        # B: Delete scattered Call Log records
        rng.shuffle(calls_records)
        calls_to_delete = calls_records[:config.num_calls_delete]
        calls_remaining = calls_records[config.num_calls_delete:]
        for r in calls_to_delete:
            cur.execute("DELETE FROM call_history WHERE id = ?", (r["id"],))
            gt.add_record(
                record_id=r["id"],
                table_name="call_history",
                values=r,
                status=expected_status,
                scenario="freeblock_scattered_delete",
                notes="Single cell deleted, converted to B-tree freeblock"
            )
        conn.commit()

        # C: Delete the burst records (forces allocation and subsequent freelist release of leaf pages)
        # If auto_vacuum is FULL (1), SQLite truncates the freelist pages on commit!
        # If auto_vacuum is NONE (0), freelist pages remain in the file!
        freelist_status = (
            RecordStatus.DELETED_OVERWRITTEN
            if (config.secure_delete == 1 or config.auto_vacuum == 1)
            else RecordStatus.DELETED_RECOVERABLE
        )
        for r in burst_records:
            cur.execute("DELETE FROM browser_history WHERE id = ?", (r["id"],))
            gt.add_record(
                record_id=r["id"],
                table_name="browser_history",
                values=r,
                status=freelist_status,
                scenario="freelist_burst_delete",
                notes="Contiguous page cluster deleted, added to freelist"
            )
        conn.commit()

        # Step 6: Updates (leaves old record content in freeblocks/slack space)
        # Update some SMS messages
        sms_to_update = sms_remaining[:config.num_sms_update]
        for r in sms_to_update:
            old_val = dict(r)
            # Update body with shorter text
            new_body = "Short OK"
            cur.execute("UPDATE messages SET body = ? WHERE id = ?", (new_body, r["id"]))
            r["body"] = new_body
            gt.add_record(
                record_id=old_val["id"],
                table_name="messages",
                values=old_val,
                status=expected_status,
                scenario="in_place_update_slack",
                notes="Updated with shorter body, old body in cell slack/freeblock"
            )
        conn.commit()

        # Update some Browser records
        browser_to_update = browser_records[:config.num_browser_update]
        for r in browser_to_update:
            old_val = dict(r)
            new_title = "Edited"
            cur.execute("UPDATE browser_history SET title = ? WHERE id = ?", (new_title, r["id"]))
            r["title"] = new_title
            gt.add_record(
                record_id=old_val["id"],
                table_name="browser_history",
                values=old_val,
                status=expected_status,
                scenario="in_place_update_slack",
                notes="Updated title, old title in slack/freeblock"
            )
        conn.commit()

        # Step 7: Record remaining live records in Ground Truth
        for r in sms_remaining:
            gt.add_record(
                record_id=r["id"],
                table_name="messages",
                values=r,
                status=RecordStatus.LIVE,
                scenario="live_record",
                notes="Active row present in table"
            )

        for r in calls_remaining:
            gt.add_record(
                record_id=r["id"],
                table_name="call_history",
                values=r,
                status=RecordStatus.LIVE,
                scenario="live_record",
                notes="Active row present in table"
            )

        # Browser live records (exclude the burst records and deleted browser records)
        rng.shuffle(browser_records)
        browser_to_delete = browser_records[:config.num_browser_delete]
        browser_remaining = browser_records[config.num_browser_delete:]
        for r in browser_to_delete:
            cur.execute("DELETE FROM browser_history WHERE id = ?", (r["id"],))
            gt.add_record(
                record_id=r["id"],
                table_name="browser_history",
                values=r,
                status=expected_status,
                scenario="freeblock_scattered_delete",
                notes="Browser history record deleted"
            )
        conn.commit()

        for r in browser_remaining:
            gt.add_record(
                record_id=r["id"],
                table_name="browser_history",
                values=r,
                status=RecordStatus.LIVE,
                scenario="live_record",
                notes="Active row present in table"
            )

        # Step 8: Distractor noise (deliberate corrupt / unparseable / high entropy strings)
        for i in range(config.distractor_count):
            distractor_body = "DISTRACTOR_NOISE_" + "".join(
                chr(rng.randint(33, 126)) for _ in range(30)
            )
            # Insert then immediately delete
            cur.execute(
                "INSERT INTO messages (thread_id, sender, recipient, timestamp, body, status) "
                "VALUES (999, 'SPAM', 'SPAM', 1700999999, ?, 0)",
                (distractor_body,)
            )
            distractor_id = cur.lastrowid
            cur.execute("DELETE FROM messages WHERE id = ?", (distractor_id,))
            gt.add_record(
                record_id=distractor_id,
                table_name="messages",
                values={"id": distractor_id, "body": distractor_body},
                status=RecordStatus.DISTRACTOR_NOISE,
                scenario="distractor_noise",
                notes="Deliberately inserted pseudo-record to test false positive resistance"
            )
        conn.commit()

        # Step 9: WAL Checkpointing if applicable
        if config.journal_mode == "WAL":
            if config.wal_checkpoint_mode:
                cur.execute(f"PRAGMA wal_checkpoint({config.wal_checkpoint_mode});")
            # If wal_checkpoint_mode is None or PASSIVE, WAL frames remain in <db>-wal!

        conn.close()

        # Compute file hashes for integrity verification
        gt.db_sha256 = compute_file_sha256(db_path)
        if wal_path.exists() and wal_path.stat().st_size > 0:
            gt.wal_filename = wal_path.name
            gt.wal_sha256 = compute_file_sha256(wal_path)

        gt_path = self.output_dir / f"{config.name}_ground_truth.json"
        gt.save_json(gt_path)

        return db_path, gt


def generate_experiment_dataset(base_dir: Path) -> Dict[str, List[Tuple[Path, DatabaseGroundTruth]]]:
    """Generate reproducible cross-validation dataset partitioned by entire database."""
    base_dir = Path(base_dir)
    splits = {
        "train": [],
        "calibration": [],
        "validation": [],
        "test": [],
        "edge_cases": [],
    }

    # Training DBs (diverse settings, seeds 101-103)
    train_configs = [
        ScenarioConfig(name="train_db_1", seed=101, secure_delete=0, auto_vacuum=0, journal_mode="DELETE"),
        ScenarioConfig(name="train_db_2", seed=102, secure_delete=0, auto_vacuum=0, journal_mode="WAL", wal_checkpoint_mode="PASSIVE"),
        ScenarioConfig(name="train_db_3", seed=103, secure_delete=0, auto_vacuum=2, journal_mode="DELETE"),
    ]

    # Calibration DBs (seeds 201-202)
    calib_configs = [
        ScenarioConfig(name="calib_db_1", seed=201, secure_delete=0, auto_vacuum=0, journal_mode="DELETE"),
        ScenarioConfig(name="calib_db_2", seed=202, secure_delete=0, auto_vacuum=0, journal_mode="WAL", wal_checkpoint_mode="PASSIVE"),
    ]

    # Validation DBs (seeds 301-302)
    val_configs = [
        ScenarioConfig(name="val_db_1", seed=301, secure_delete=0, auto_vacuum=0, journal_mode="DELETE"),
        ScenarioConfig(name="val_db_2", seed=302, secure_delete=0, auto_vacuum=0, journal_mode="WAL", wal_checkpoint_mode="PASSIVE"),
    ]

    # Final Test DBs (seeds 401-403)
    test_configs = [
        ScenarioConfig(name="test_db_1", seed=401, secure_delete=0, auto_vacuum=0, journal_mode="DELETE"),
        ScenarioConfig(name="test_db_2", seed=402, secure_delete=0, auto_vacuum=0, journal_mode="WAL", wal_checkpoint_mode="PASSIVE"),
        ScenarioConfig(name="test_db_3", seed=403, secure_delete=0, auto_vacuum=0, journal_mode="DELETE"),
    ]

    # Specialized Edge Cases (Anti-forensics & unrecoverable scenarios)
    edge_configs = [
        ScenarioConfig(name="edge_secure_delete_on", seed=501, secure_delete=1, auto_vacuum=0, journal_mode="DELETE"),
        ScenarioConfig(name="edge_auto_vacuum_full", seed=502, secure_delete=0, auto_vacuum=1, journal_mode="DELETE"),
        ScenarioConfig(name="edge_wal_checkpoint_restart", seed=503, secure_delete=0, auto_vacuum=0, journal_mode="WAL", wal_checkpoint_mode="RESTART"),
    ]

    gen = ForensicDatabaseGenerator(base_dir)

    for cfg in train_configs:
        splits["train"].append(gen.generate(cfg))
    for cfg in calib_configs:
        splits["calibration"].append(gen.generate(cfg))
    for cfg in val_configs:
        splits["validation"].append(gen.generate(cfg))
    for cfg in test_configs:
        splits["test"].append(gen.generate(cfg))
    for cfg in edge_configs:
        splits["edge_cases"].append(gen.generate(cfg))

    return splits
