#!/usr/bin/env python3
"""
adapter-db.py — SQLite log database for the .claude framework.
Replaces scattered JSONL files with a single logs.db.

Usage:
  adapter-db.py init                              Create db + tables (idempotent)
  adapter-db.py insert <source> [log_key] <json>   Insert one event
  adapter-db.py query <source> [--tail N] [...]    Query events
  adapter-db.py rotate <source> --keep N           Keep last N, delete older
  adapter-db.py migrate <jsonl_path> <source>      Import existing JSONL
  adapter-db.py stats                              Summary statistics
  adapter-db.py vacuum                             Optimize db

All commands are idempotent and safe to re-run.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("USERPROFILE", "~")) / ".claude" / ".claude" / "logs.db"


def get_db() -> sqlite3.Connection:
    """Get connection, auto-creating db if needed."""
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = sqlite3.Row
    return db


def init_db() -> str:
    """Create tables and indexes if they don't exist. Idempotent."""
    db = get_db()
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
        CREATE INDEX IF NOT EXISTS idx_events_source_id ON events(source, id DESC);
        CREATE INDEX IF NOT EXISTS idx_events_log_key ON events(source, log_key);
    """)
    db.commit()
    cnt = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    db.close()
    return f"OK: {cnt} events, {size:,} bytes"


def insert_event(source: str, log_key: str | None, data_json: str) -> str:
    """Insert a single event. data_json is the JSON string."""
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return f"ERROR: invalid JSON: {data_json[:80]}"

    # Extract timestamp from data if present (common field names)
    ts = data.get("timestamp") or data.get("t") or datetime.now(timezone.utc).isoformat()

    db = get_db()
    db.execute(
        "INSERT INTO events (source, log_key, timestamp, data) VALUES (?, ?, ?, ?)",
        (source, log_key, ts, data_json)
    )
    db.commit()
    rowid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return f"OK: inserted id={rowid}"


def query_events(source: str, tail: int = 20, after: str | None = None,
                 before: str | None = None, key: str | None = None,
                 where: str | None = None, output_json: bool = False) -> str:
    """Query events. Returns JSON array or count."""
    db = get_db()
    conditions = ["source = ?"]
    params = [source]

    if after:
        conditions.append("timestamp > ?")
        params.append(after)
    if before:
        conditions.append("timestamp < ?")
        params.append(before)
    if key:
        conditions.append("log_key LIKE ?")
        params.append(key)
    if where:
        conditions.append(f"({where})")

    where_clause = " AND ".join(conditions)
    query = f"SELECT data FROM events WHERE {where_clause} ORDER BY id DESC"
    if tail > 0:
        query += f" LIMIT {tail}"

    rows = [json.loads(row[0]) for row in db.execute(query, params).fetchall()]
    db.close()

    if output_json:
        return json.dumps(rows, ensure_ascii=False)
    return json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False)


def rotate_events(source: str, keep: int) -> str:
    """Keep last N events for source, delete older ones."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM events WHERE source = ?", (source,)).fetchone()[0]
    if total <= keep:
        db.close()
        return f"OK: {total} events, no rotation needed (limit={keep})"

    db.execute("""
        DELETE FROM events WHERE source = ? AND id NOT IN (
            SELECT id FROM events WHERE source = ? ORDER BY id DESC LIMIT ?
        )
    """, (source, source, keep))
    deleted = total - keep
    db.commit()
    db.close()
    return f"OK: deleted {deleted}, kept {keep}"


def migrate_jsonl(jsonl_path: str, source: str, log_key: str | None = None) -> str:
    """Import existing JSONL file into the database."""
    path = Path(jsonl_path)
    if not path.exists():
        return f"SKIP: {jsonl_path} not found"

    db = get_db()
    inserted = 0
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue

        ts = data.get("timestamp") or data.get("t") or ""
        lk = log_key or data.get("h") or data.get("hook") or ""
        db.execute(
            "INSERT INTO events (source, log_key, timestamp, data) VALUES (?, ?, ?, ?)",
            (source, lk, ts, line)
        )
        inserted += 1

    db.commit()
    db.close()
    return f"OK: {inserted} inserted, {skipped} skipped from {jsonl_path}"


def get_stats() -> str:
    """Return summary statistics."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    sources = db.execute(
        "SELECT source, COUNT(*) as cnt, MIN(row_created), MAX(row_created) "
        "FROM events GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    db.close()

    lines = [f"Total: {total:,} events, {size:,} bytes", f"Sources: {len(sources)}", ""]
    for s in sources[:20]:
        lines.append(f"  {s['source']}: {s['cnt']:,} events")
    if len(sources) > 20:
        lines.append(f"  ... and {len(sources) - 20} more")
    return "\n".join(lines)


def vacuum_db() -> str:
    """Optimize database."""
    db = get_db()
    before = DB_PATH.stat().st_size
    db.execute("VACUUM")
    db.close()
    after = DB_PATH.stat().st_size
    return f"OK: {before:,} → {after:,} bytes (saved {before - after:,})"


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: adapter-db.py <init|insert|query|rotate|migrate|stats|vacuum> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "init":
            print(init_db())

        elif cmd == "insert":
            if len(sys.argv) < 4:
                print("Usage: adapter-db.py insert <source> [log_key] <json>")
                print("  If log_key is omitted, extracted from json data")
                sys.exit(1)
            source = sys.argv[2]
            # Determine if 3rd arg is log_key or json
            if len(sys.argv) == 4:
                # adapter-db.py insert source json
                data = sys.argv[3]
                log_key = ""
            elif len(sys.argv) == 5:
                # adapter-db.py insert source log_key json
                log_key = sys.argv[3]
                data = sys.argv[4]
            else:
                print("Usage: adapter-db.py insert <source> [log_key] <json>")
                sys.exit(1)
            print(insert_event(source, log_key if log_key else None, data))

        elif cmd == "query":
            source = sys.argv[2] if len(sys.argv) > 2 else ""
            if not source:
                print("Usage: adapter-db.py query <source> [--tail N] [--after TS] [--json]")
                sys.exit(1)

            tail = 20
            after = None
            before = None
            key = None
            where = None
            as_json = False

            args = sys.argv[3:]
            i = 0
            while i < len(args):
                if args[i] == "--tail" and i + 1 < len(args):
                    tail = int(args[i + 1]); i += 2
                elif args[i] == "--after" and i + 1 < len(args):
                    after = args[i + 1]; i += 2
                elif args[i] == "--before" and i + 1 < len(args):
                    before = args[i + 1]; i += 2
                elif args[i] == "--key" and i + 1 < len(args):
                    key = args[i + 1]; i += 2
                elif args[i] == "--where" and i + 1 < len(args):
                    where = args[i + 1]; i += 2
                elif args[i] == "--json":
                    as_json = True; i += 1
                else:
                    i += 1

            print(query_events(source, tail, after, before, key, where, as_json))

        elif cmd == "rotate":
            if len(sys.argv) < 5 or sys.argv[3] != "--keep":
                print("Usage: adapter-db.py rotate <source> --keep N")
                sys.exit(1)
            source = sys.argv[2]
            keep = int(sys.argv[4])
            print(rotate_events(source, keep))

        elif cmd == "migrate":
            if len(sys.argv) < 4:
                print("Usage: adapter-db.py migrate <jsonl_path> <source> [log_key]")
                sys.exit(1)
            path = sys.argv[2]
            source = sys.argv[3]
            log_key = sys.argv[4] if len(sys.argv) > 4 else None
            print(migrate_jsonl(path, source, log_key))

        elif cmd == "stats":
            print(get_stats())

        elif cmd == "vacuum":
            print(vacuum_db())

        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
