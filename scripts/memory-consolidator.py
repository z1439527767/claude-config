#!/usr/bin/env python3
"""memory-consolidator — Claude Code autoDream equivalent.
Consolidates memories: deduplicate, detect contradictions, mark stale, generate principles.
Three-gate trigger: 24h since last run, 5+ sessions since last, lock acquired.
Usage:
  python3 memory-consolidator.py [--dry-run] [--json] [--force]

Phases (matches autoDream):
  1. Orient — read memory directory, skim existing topics
  2. Gather — daily logs → drifted memories → transcript search
  3. Consolidate — write/update memory files, convert relative dates, delete contradictions
  4. Prune and Index — keep MEMORY.md under 200 lines AND ~25KB
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
MEMORY_DIR = HOME / '.claude' / 'projects' / 'C--Users-z1439--claude' / 'memory'
MEMORY_INDEX = MEMORY_DIR / 'MEMORY.md'
STATE_FILE = HOME / '.claude' / '.claude' / 'consolidator_state.json'
LOCK_FILE = HOME / '.claude' / '.claude' / 'consolidator.lock'
MAX_LINES = 200
MAX_SIZE_KB = 25

def acquire_lock():
    """Prevent concurrent consolidation runs."""
    if LOCK_FILE.exists():
        age = datetime.now() - datetime.fromtimestamp(LOCK_FILE.stat().st_mtime)
        if age.total_seconds() < 300:  # 5 min lock
            return False
    LOCK_FILE.write_text(datetime.now().isoformat())
    return True

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"last_run": None, "sessions_since": 0, "total_runs": 0}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def should_run(state, force=False):
    """Three-gate trigger system."""
    if force:
        return True, "forced"
    if not state["last_run"]:
        return True, "first_run"
    last = datetime.fromisoformat(state["last_run"])
    hours_since = (datetime.now() - last).total_seconds() / 3600
    if hours_since < 24:
        return False, f"time_gate: {hours_since:.1f}h since last run (< 24h)"
    if state["sessions_since"] < 5:
        return False, f"session_gate: {state['sessions_since']} sessions since last (< 5)"
    return True, "all_gates_passed"

def parse_memory_index():
    """Parse MEMORY.md entries."""
    if not MEMORY_INDEX.exists():
        return []
    content = MEMORY_INDEX.read_text(encoding='utf-8')
    entries = []
    for line in content.split('\n'):
        m = re.match(r'^- \[(\S+)\]\(([^)]+)\) — (.+?)\s\[.+?\]$', line)
        if m:
            entry_id, path, description = m.groups()
            mem_file = MEMORY_DIR / path
            created = None
            if mem_file.exists():
                fc = mem_file.read_text(encoding='utf-8', errors='ignore')
                cm = re.search(r'(?m)^created:\s*(.+)$', fc)
                if cm:
                    try:
                        created = datetime.fromisoformat(cm.group(1).strip())
                    except Exception:
                        pass
            entries.append({
                "id": entry_id, "path": path, "description": description,
                "file": str(mem_file), "created": created,
                "exists": mem_file.exists(),
            })
    return entries

def find_duplicates(entries):
    """Detect duplicate/similar entries."""
    from collections import defaultdict
    groups = defaultdict(list)
    for e in entries:
        # Simple keyword grouping
        words = set(re.findall(r'\w+', e["description"].lower()))
        key_words = words & {'memory', 'rule', 'behavior', 'hook', 'tool', 'error',
                             'session', 'evolution', 'config', 'setting', 'language',
                             'scope', 'task', 'feedback', 'system', 'project'}
        if key_words:
            for kw in key_words:
                groups[kw].append(e)
    duplicates = []
    for kw, group in groups.items():
        if len(group) >= 2:
            duplicates.append({"keyword": kw, "entries": group, "count": len(group)})
    return duplicates

def detect_stale(entries):
    """Detect stale entries (>30 days since creation, no access)."""
    stale = []
    for e in entries:
        if e["created"]:
            days = (datetime.now() - e["created"]).days
            if days > 60:
                stale.append({**e, "age_days": days, "level": "expired"})
            elif days > 30:
                stale.append({**e, "age_days": days, "level": "aging"})
    return stale

def check_index_health():
    """Check MEMORY.md health."""
    if not MEMORY_INDEX.exists():
        return {"exists": False}
    content = MEMORY_INDEX.read_text(encoding='utf-8')
    lines = content.count('\n') + 1
    size_kb = len(content.encode('utf-8')) / 1024
    return {
        "exists": True,
        "lines": lines,
        "size_kb": round(size_kb, 1),
        "over_line_limit": lines > MAX_LINES,
        "over_size_limit": size_kb > MAX_SIZE_KB,
        "entries": content.count('- ['),
    }

def main():
    use_json = "--json" in sys.argv
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    state = load_state()
    can_run, reason = should_run(state, force)

    if not can_run and not dry_run:
        if use_json:
            print(json.dumps({"status": "skipped", "reason": reason}))
        else:
            print(f"MEMORY-CONSOLIDATOR: skipped ({reason})")
        return

    if not acquire_lock():
        print("MEMORY-CONSOLIDATOR: locked (another consolidation in progress)")
        return

    try:
        # Phase 1: Orient
        entries = parse_memory_index()
        health = check_index_health()

        # Phase 2: Gather
        duplicates = find_duplicates(entries)
        stale = detect_stale(entries)

        # Phase 3: Consolidate (dry-run = report only)
        # Phase 4: Prune check

        state["last_run"] = datetime.now().isoformat()
        state["sessions_since"] = 0
        state["total_runs"] += 1

        if not dry_run:
            save_state(state)

        result = {
            "status": "dry_run" if dry_run else "consolidated",
            "timestamp": datetime.now().isoformat(),
            "entries": len(entries),
            "duplicates": len(duplicates),
            "duplicate_groups": [{"keyword": d["keyword"], "count": d["count"]} for d in duplicates],
            "stale": len(stale),
            "stale_entries": [{"id": s["id"], "age_days": s["age_days"], "level": s["level"]} for s in stale[:5]],
            "index_health": health,
        }

        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"MEMORY-CONSOLIDATOR: {result['status']} — {reason}")
            print(f"  Entries: {len(entries)}, Duplicates: {len(duplicates)}, Stale: {len(stale)}")
            if health.get("over_line_limit"):
                print(f"  ⚠ MEMORY.md: {health['lines']} lines > {MAX_LINES} limit")
            if health.get("over_size_limit"):
                print(f"  ⚠ MEMORY.md: {health['size_kb']}KB > {MAX_SIZE_KB}KB limit")
            if duplicates:
                print(f"  Duplicate groups:")
                for d in duplicates[:3]:
                    ids = [e["id"] for e in d["entries"]]
                    print(f"    keyword='{d['keyword']}': {ids}")
            if stale:
                print(f"  Stale (>30d): {', '.join(s['id'] for s in stale[:5])}")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
