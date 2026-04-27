from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterator


def _db_path() -> str:
    return os.environ.get("GRAPHIC_STUDIO_DB", "graphic_studio.db")


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              brief TEXT NOT NULL,
              latest_artifact TEXT,
              pending_gate TEXT,
              variant INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS job_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              body_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);
            """
        )


@dataclass
class JobRecord:
    id: str
    status: str
    brief: str
    latest_artifact: str | None
    pending_gate: str | None
    variant: int
    created_at: str
    updated_at: str


def create_job(brief: str) -> JobRecord:
    init_schema()
    job_id = str(uuid.uuid4())
    now = _now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, status, brief, latest_artifact, pending_gate, variant, created_at, updated_at)
            VALUES (?, ?, ?, NULL, NULL, 0, ?, ?)
            """,
            (job_id, "new", brief, now, now),
        )
    return get_job(job_id)


def get_job(job_id: str) -> JobRecord:
    init_schema()
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return JobRecord(
        id=row["id"],
        status=row["status"],
        brief=row["brief"],
        latest_artifact=row["latest_artifact"],
        pending_gate=row["pending_gate"],
        variant=row["variant"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    latest_artifact: str | None = None,
    pending_gate: str | None = None,
    variant: int | None = None,
    brief: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if latest_artifact is not None:
        fields.append("latest_artifact = ?")
        values.append(latest_artifact)
    if pending_gate is not None:
        fields.append("pending_gate = ?")
        values.append(pending_gate)
    if variant is not None:
        fields.append("variant = ?")
        values.append(variant)
    if brief is not None:
        fields.append("brief = ?")
        values.append(brief)
    fields.append("updated_at = ?")
    values.append(_now_iso())
    values.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
    with connect() as conn:
        conn.execute(sql, values)


def append_event(job_id: str, kind: str, body: dict[str, Any]) -> None:
    init_schema()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO job_events (job_id, kind, body_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, kind, json.dumps(body), _now_iso()),
        )


def list_events(job_id: str) -> list[dict[str, Any]]:
    init_schema()
    with connect() as conn:
        rows = conn.execute(
            "SELECT kind, body_json, created_at FROM job_events WHERE job_id = ? ORDER BY id ASC",
            (job_id,),
        ).fetchall()
    return [{"kind": r["kind"], "body": json.loads(r["body_json"]), "created_at": r["created_at"]} for r in rows]
