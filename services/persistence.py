"""Small SQLite job repository; video bytes remain on the filesystem."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class JobRecord:
    id: str
    input_filename: str
    status: str
    created_at: str
    event_count: int = 0
    processing_duration: float | None = None
    output_location: str | None = None
    error: str | None = None


class JobRepository:
    def __init__(self, database_url: str) -> None:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("This build supports SQLite DATABASE_URL values only.")
        self.path = Path(database_url[len(prefix) :])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, input_filename TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, event_count INTEGER NOT NULL DEFAULT 0,
                processing_duration REAL, output_location TEXT, error TEXT
                )"""
            )

    def create(self, job_id: str, input_filename: str) -> JobRecord:
        record = JobRecord(
            id=job_id,
            input_filename=input_filename,
            status="created",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES "
                "(:id, :input_filename, :status, :created_at, :event_count, "
                ":processing_duration, :output_location, :error)",
                asdict(record),
            )
        return record

    def update(self, job_id: str, **fields: object) -> None:
        allowed = {"status", "event_count", "processing_duration", "output_location", "error"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = :{key}" for key in values)
        values["id"] = job_id
        with self._connect() as connection:
            connection.execute(f"UPDATE jobs SET {assignments} WHERE id = :id", values)  # noqa: S608

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return JobRecord(**dict(row)) if row else None
