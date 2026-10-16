"""Ground truth data models and evidence integrity preservation."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class RecordStatus(str, Enum):
    LIVE = "LIVE"
    DELETED_RECOVERABLE = "DELETED_RECOVERABLE"
    DELETED_OVERWRITTEN = "DELETED_OVERWRITTEN"
    UPDATED_OLD_VERSION = "UPDATED_OLD_VERSION"
    DISTRACTOR_NOISE = "DISTRACTOR_NOISE"


@dataclass
class GroundTruthRecord:
    """Represents a known ground-truth record state."""
    record_id: int
    table_name: str
    values: Dict[str, Any]
    status: RecordStatus
    scenario: str
    sha256: str
    notes: str = ""

    @classmethod
    def compute_hash(cls, table_name: str, values: Dict[str, Any]) -> str:
        """Compute canonical SHA-256 hash of a table row's field values."""
        # Sort keys for deterministic hash
        canonical = json.dumps(
            {"table": table_name, "values": values},
            sort_keys=True,
            default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundTruthRecord":
        return cls(
            record_id=data["record_id"],
            table_name=data["table_name"],
            values=data["values"],
            status=RecordStatus(data["status"]),
            scenario=data["scenario"],
            sha256=data["sha256"],
            notes=data.get("notes", ""),
        )


@dataclass
class DatabaseGroundTruth:
    """Ground truth catalog for a single SQLite database instance."""
    database_id: str
    db_filename: str
    db_sha256: str
    wal_filename: Optional[str] = None
    wal_sha256: Optional[str] = None
    seed: int = 42
    sqlite_config: Dict[str, Any] = field(default_factory=dict)
    records: List[GroundTruthRecord] = field(default_factory=list)

    def add_record(
        self,
        record_id: int,
        table_name: str,
        values: Dict[str, Any],
        status: RecordStatus,
        scenario: str,
        notes: str = ""
    ) -> GroundTruthRecord:
        h = GroundTruthRecord.compute_hash(table_name, values)
        rec = GroundTruthRecord(
            record_id=record_id,
            table_name=table_name,
            values=values,
            status=status,
            scenario=scenario,
            sha256=h,
            notes=notes
        )
        self.records.append(rec)
        return rec

    def get_live_records(self, table_name: Optional[str] = None) -> List[GroundTruthRecord]:
        return [
            r for r in self.records
            if r.status == RecordStatus.LIVE and (table_name is None or r.table_name == table_name)
        ]

    def get_deleted_records(self, table_name: Optional[str] = None) -> List[GroundTruthRecord]:
        return [
            r for r in self.records
            if r.status in (RecordStatus.DELETED_RECOVERABLE, RecordStatus.UPDATED_OLD_VERSION)
            and (table_name is None or r.table_name == table_name)
        ]

    def save_json(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "database_id": self.database_id,
            "db_filename": self.db_filename,
            "db_sha256": self.db_sha256,
            "wal_filename": self.wal_filename,
            "wal_sha256": self.wal_sha256,
            "seed": self.seed,
            "sqlite_config": self.sqlite_config,
            "records": [r.to_dict() for r in self.records],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_json(cls, path: Path) -> "DatabaseGroundTruth":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        instance = cls(
            database_id=data["database_id"],
            db_filename=data["db_filename"],
            db_sha256=data["db_sha256"],
            wal_filename=data.get("wal_filename"),
            wal_sha256=data.get("wal_sha256"),
            seed=data["seed"],
            sqlite_config=data.get("sqlite_config", {}),
            records=[GroundTruthRecord.from_dict(r) for r in data["records"]],
        )
        return instance


def compute_file_sha256(path: Path) -> str:
    """Compute cryptographic SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
