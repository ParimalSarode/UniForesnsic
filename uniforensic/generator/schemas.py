"""Table schemas and realistic record generators for forensic SQLite databases."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import random
import time


@dataclass
class ColumnDef:
    name: str
    affinity: str  # INTEGER, TEXT, REAL, BLOB
    nullable: bool = True
    is_primary_key: bool = False


@dataclass
class TableSchema:
    name: str
    columns: List[ColumnDef]
    create_sql: str

    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


SMS_SCHEMA = TableSchema(
    name="messages",
    columns=[
        ColumnDef("id", "INTEGER", nullable=False, is_primary_key=True),
        ColumnDef("thread_id", "INTEGER", nullable=False),
        ColumnDef("sender", "TEXT", nullable=False),
        ColumnDef("recipient", "TEXT", nullable=False),
        ColumnDef("timestamp", "INTEGER", nullable=False),
        ColumnDef("body", "TEXT", nullable=False),
        ColumnDef("status", "INTEGER", nullable=False),
        ColumnDef("attachment_path", "TEXT", nullable=True),
    ],
    create_sql="""
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id INTEGER NOT NULL,
        sender TEXT NOT NULL,
        recipient TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        body TEXT NOT NULL,
        status INTEGER NOT NULL,
        attachment_path TEXT
    );
    """
)

CALL_LOG_SCHEMA = TableSchema(
    name="call_history",
    columns=[
        ColumnDef("id", "INTEGER", nullable=False, is_primary_key=True),
        ColumnDef("phone_number", "TEXT", nullable=False),
        ColumnDef("call_type", "INTEGER", nullable=False),
        ColumnDef("timestamp", "INTEGER", nullable=False),
        ColumnDef("duration", "INTEGER", nullable=False),
        ColumnDef("contact_name", "TEXT", nullable=True),
        ColumnDef("sim_id", "INTEGER", nullable=False),
    ],
    create_sql="""
    CREATE TABLE call_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone_number TEXT NOT NULL,
        call_type INTEGER NOT NULL,
        timestamp INTEGER NOT NULL,
        duration INTEGER NOT NULL,
        contact_name TEXT,
        sim_id INTEGER NOT NULL DEFAULT 1
    );
    """
)

BROWSER_HISTORY_SCHEMA = TableSchema(
    name="browser_history",
    columns=[
        ColumnDef("id", "INTEGER", nullable=False, is_primary_key=True),
        ColumnDef("url", "TEXT", nullable=False),
        ColumnDef("title", "TEXT", nullable=False),
        ColumnDef("visit_time", "INTEGER", nullable=False),
        ColumnDef("visit_count", "INTEGER", nullable=False),
        ColumnDef("typed_count", "INTEGER", nullable=False),
        ColumnDef("hidden", "INTEGER", nullable=False),
    ],
    create_sql="""
    CREATE TABLE browser_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        visit_time INTEGER NOT NULL,
        visit_count INTEGER NOT NULL DEFAULT 1,
        typed_count INTEGER NOT NULL DEFAULT 0,
        hidden INTEGER NOT NULL DEFAULT 0
    );
    """
)

SCHEMAS: Dict[str, TableSchema] = {
    "messages": SMS_SCHEMA,
    "call_history": CALL_LOG_SCHEMA,
    "browser_history": BROWSER_HISTORY_SCHEMA,
}


class SyntheticRecordFactory:
    """Generates realistic synthetic records with deterministic pseudo-random control."""

    CONTACTS = [
        ("Alice Cooper", "+15550192834"),
        ("Bob Smith", "+15550293847"),
        ("Carol Danvers", "+15550384756"),
        ("David Miller", "+15550475628"),
        ("Eve Adams", "+15550564738"),
        ("Frank Castle", "+15550653829"),
        ("Grace Hopper", "+15550742910"),
        ("Heidi Fleiss", "+15550831092"),
    ]

    SMS_SNIPPETS = [
        "Hey, are we still meeting at 3 PM today?",
        "Attached the updated contract document for your review.",
        "Your verification code is 482910. Do not share this with anyone.",
        "Flight UA249 is on schedule. See you at terminal 2.",
        "Can you send over the encrypted database password?",
        "Package has been delivered to your front porch.",
        "Reminder: Doctor appointment tomorrow morning at 9:00.",
        "Thanks for the dinner yesterday! Let's catch up soon.",
        "Emergency: please call me back as soon as you get this.",
        "The server deployment finished with 0 errors.",
    ]

    DOMAINS = [
        ("https://github.com/torvalds/linux", "GitHub - Linux Kernel Source Tree"),
        ("https://stackoverflow.com/questions/sqlite-recovery", "sqlite recovery - Stack Overflow"),
        ("https://www.nytimes.com/section/technology", "Technology News and Analysis - The New York Times"),
        ("https://en.wikipedia.org/wiki/Digital_forensics", "Digital forensics - Wikipedia"),
        ("https://sqlite.org/fileformat2.html", "Database File Format - SQLite"),
        ("https://docs.python.org/3/library/sqlite3.html", "sqlite3 — DB-API 2.0 interface — Python documentation"),
        ("https://news.ycombinator.com/", "Hacker News"),
        ("https://duckduckgo.com/?q=forensic+artifacts", "forensic artifacts at DuckDuckGo"),
    ]

    def __init__(self, rng: random.Random, base_timestamp: int = 1700000000):
        self.rng = rng
        self.base_timestamp = base_timestamp

    def generate_sms(self, record_id: int) -> Dict[str, Any]:
        contact, phone = self.rng.choice(self.CONTACTS)
        is_sender = self.rng.choice([True, False])
        sender = "+15550999999" if is_sender else phone
        recipient = phone if is_sender else "+15550999999"
        thread_id = abs(hash(phone)) % 1000 + 1
        ts = self.base_timestamp + self.rng.randint(0, 86400 * 30)
        body = self.rng.choice(self.SMS_SNIPPETS)
        has_attachment = self.rng.random() < 0.2
        attachment = f"/data/media/{self.rng.randint(1000, 9999)}.jpg" if has_attachment else None

        return {
            "id": record_id,
            "thread_id": thread_id,
            "sender": sender,
            "recipient": recipient,
            "timestamp": ts,
            "body": body,
            "status": self.rng.choice([0, 1, 2]),
            "attachment_path": attachment,
        }

    def generate_call(self, record_id: int) -> Dict[str, Any]:
        contact, phone = self.rng.choice(self.CONTACTS)
        call_type = self.rng.choice([1, 2, 3, 4])
        duration = 0 if call_type == 3 else self.rng.randint(5, 3600)
        ts = self.base_timestamp + self.rng.randint(0, 86400 * 30)

        return {
            "id": record_id,
            "phone_number": phone,
            "call_type": call_type,
            "timestamp": ts,
            "duration": duration,
            "contact_name": contact,
            "sim_id": self.rng.choice([1, 2]),
        }

    def generate_browser_history(self, record_id: int) -> Dict[str, Any]:
        url, title = self.rng.choice(self.DOMAINS)
        ts = self.base_timestamp + self.rng.randint(0, 86400 * 30)

        return {
            "id": record_id,
            "url": url,
            "title": title,
            "visit_time": ts,
            "visit_count": self.rng.randint(1, 25),
            "typed_count": self.rng.randint(0, 5),
            "hidden": 0 if self.rng.random() > 0.05 else 1,
        }

    def generate_record(self, table_name: str, record_id: int) -> Dict[str, Any]:
        if table_name == "messages":
            return self.generate_sms(record_id)
        elif table_name == "call_history":
            return self.generate_call(record_id)
        elif table_name == "browser_history":
            return self.generate_browser_history(record_id)
        else:
            raise ValueError(f"Unknown table name: {table_name}")
