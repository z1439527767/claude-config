#!/usr/bin/env python3
"""
db.py — Importable Python module for SQLite log operations.
Used by Python scripts (auto-heal, neuromodulation, immune-system, watchdog, etc.)
to write to the unified logs.db without calling the CLI adapter.

Usage:
    from db import write_log, query_log, rotate_log
    write_log("auto_heal", None, {"timestamp": "...", "action": "fix"})
    results = query_log("auto_heal", tail=50)
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("USERPROFILE", "~")) / ".claude" / ".claude" / "logs.db"


def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = sqlite3.Row
    # Auto-create schema if missing
    db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            log_key TEXT,
            timestamp TEXT,
            data TEXT NOT NULL,
            row_created TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
        CREATE INDEX IF NOT EXISTS idx_events_source_ts ON events(source, timestamp);
    """)
    db.commit()
    return db


def write_log(source: str, log_key: str | None, data: dict) -> int:
    """Insert one event. Returns the new row id."""
    data_json = json.dumps(data, ensure_ascii=False)
    ts = data.get("timestamp") or data.get("t") or datetime.now(timezone.utc).isoformat()
    db = _get_db()
    db.execute(
        "INSERT INTO events (source, log_key, timestamp, data) VALUES (?, ?, ?, ?)",
        (source, log_key, ts, data_json)
    )
    db.commit()
    rowid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return rowid


def query_log(source: str, tail: int = 50, after: str | None = None,
              before: str | None = None, key: str | None = None) -> list[dict]:
    """Query events for a source. Returns list of parsed JSON dicts."""
    db = _get_db()
    conditions = ["source = ?"]
    params = [source]
    if after:
        conditions.append("timestamp > ?"); params.append(after)
    if before:
        conditions.append("timestamp < ?"); params.append(before)
    if key:
        conditions.append("log_key LIKE ?"); params.append(key)

    where_clause = " AND ".join(conditions)
    query = f"SELECT data FROM events WHERE {where_clause} ORDER BY id DESC"
    if tail > 0:
        query += f" LIMIT {tail}"

    rows = [json.loads(row[0]) for row in db.execute(query, params).fetchall()]
    db.close()
    return rows


def rotate_log(source: str, keep: int) -> int:
    """Keep last N events for source. Returns number deleted."""
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM events WHERE source = ?", (source,)).fetchone()[0]
    if total <= keep:
        db.close()
        return 0
    db.execute("""
        DELETE FROM events WHERE source = ? AND id NOT IN (
            SELECT id FROM events WHERE source = ? ORDER BY id DESC LIMIT ?
        )
    """, (source, source, keep))
    db.commit()
    deleted = total - keep
    db.close()
    return deleted


def get_stats() -> dict:
    """Return summary statistics."""
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    sources = db.execute(
        "SELECT source, COUNT(*) as cnt FROM events GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    db.close()
    return {
        "total_events": total,
        "sources": len(sources),
        "size_bytes": size,
        "by_source": {s["source"]: s["cnt"] for s in sources},
    }
