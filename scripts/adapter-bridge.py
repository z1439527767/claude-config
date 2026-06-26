#!/usr/bin/env python3
"""
adapter-bridge.py — Unified Python↔PowerShell bridge for the .claude framework.

Replaces scattered data-bridge.py. Handles:
  1. State passing: PS hooks → Python scripts → PS hooks
  2. Context injection: Python output → formatted for LLM context
  3. Event routing: hook events → correct Python handler
  4. Memory sync bridge: file memory ↔ KG API calls
  5. Health metrics: aggregate health data for adapter-state.ps1

Usage:
  python adapter-bridge.py state          # dump current bridge state
  python adapter-bridge.py inject <key>   # get injection text for context
  python adapter-bridge.py route <event> [payload]  # route event to handler
  python adapter-bridge.py health         # health metrics JSON
  python adapter-bridge.py sync-memory    # sync file memory → KG
  python adapter-bridge.py serve          # daemon mode (stdin JSON, stdout JSON)
"""

import json
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

BASE_DIR = Path(os.environ.get("USERPROFILE", "~")) / ".claude"
SCRIPTS_DIR = BASE_DIR / "scripts"
_mem_dirs = list((BASE_DIR / "projects").glob("*/memory"))
MEMORY_DIR = _mem_dirs[0] if _mem_dirs else BASE_DIR / "projects" / f"C--Users-{os.environ.get('USERNAME','z1439')}--claude" / "memory"
STATE_DIR = BASE_DIR / ".claude"
LOGS_DIR = BASE_DIR / "logs"
BRIDGE_STATE_FILE = STATE_DIR / "bridge_state.json"


# ═══════════════════════════════════════════
# BRIDGE STATE
# ═══════════════════════════════════════════

def load_bridge_state() -> dict:
    if BRIDGE_STATE_FILE.exists():
        try:
            return json.loads(BRIDGE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "version": "2.0",
        "created": datetime.now(timezone.utc).isoformat(),
        "last_event": None,
        "event_count": 0,
        "injections": {},
        "errors": [],
    }


def save_bridge_state(state: dict) -> None:
    state["updated"] = datetime.now(timezone.utc).isoformat()
    BRIDGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRIDGE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════
# HEALTH METRICS
# ═══════════════════════════════════════════

def get_health() -> dict:
    """Aggregate health metrics from all sources."""
    health = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_scripts": count_python_scripts(),
        "memory_files": count_memory_files(),
        "bridge_errors": len(load_bridge_state().get("errors", [])),
    }

    # Check if critical files exist
    for f in ["CLAUDE.md", "AGENTS.md", "settings.json"]:
        health[f"has_{f.replace('.', '_')}"] = (BASE_DIR / f).exists()

    return health


def count_python_scripts() -> int:
    return len(list(SCRIPTS_DIR.glob("*.py")))


def count_memory_files() -> int:
    if not MEMORY_DIR.exists():
        return 0
    return len([f for f in MEMORY_DIR.rglob("*.md") if f.name != "MEMORY.md"])


# ═══════════════════════════════════════════
# CONTEXT INJECTION
# ═══════════════════════════════════════════

INJECTORS = {
    "memory": "memory-search.py",
    "identity": "identity-journal.py",
    "intuition": "intuition-engine.py",
    "immune": "immune-system.py",
    "narrative": "narrative-engine.py",
    "salience": "salience-gate.py",
    "interoception": "interoception.py",
    "neuromodulation": "neuromodulation.py",
}


def inject(key: str) -> str:
    """Get injection text for a given key. Runs the corresponding Python script."""
    if key == "all":
        results = {}
        for k in INJECTORS:
            results[k] = inject_one(k)
        return json.dumps(results, ensure_ascii=False)
    return inject_one(key)


def inject_one(key: str) -> str | None:
    """Run a single injector and return its output."""
    if key not in INJECTORS:
        return None
    script = SCRIPTS_DIR / INJECTORS[key]
    if not script.exists():
        return None
    import subprocess
    try:
        result = subprocess.run(
            ["python", str(script), "--inject"],
            capture_output=True, text=True, timeout=5, cwd=str(BASE_DIR)
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════
# EVENT ROUTING
# ═══════════════════════════════════════════

EVENT_ROUTES = {
    "SessionStart": ["memory-search.py", "identity-journal.py", "intuition-engine.py"],
    "SessionEnd": ["session-summarizer.py", "subconscious.py"],
    "Stop": ["session-summarizer.py"],
    "UserPromptSubmit": ["frustration-watch", "detect-input-lang"],
}


def route_event(event: str, payload: str | None = None) -> dict:
    """Route a hook event to the correct Python handler(s)."""
    state = load_bridge_state()
    state["last_event"] = event
    state["event_count"] += 1

    handlers = EVENT_ROUTES.get(event, [])
    results = {}

    for handler in handlers:
        script = SCRIPTS_DIR / f"{handler}.py" if not handler.endswith(".py") else SCRIPTS_DIR / handler
        # Handle hook-based handlers (ps1 wrappers that call python)
        if not script.exists():
            script = SCRIPTS_DIR / "hooks" / f"{handler}.ps1"
        if not script.exists():
            results[handler] = {"status": "not_found"}
            continue
        results[handler] = {"status": "found", "path": str(script)}

    save_bridge_state(state)
    return {"event": event, "routed_to": list(results.keys()), "results": results}


# ═══════════════════════════════════════════
# MEMORY SYNC BRIDGE
# ═══════════════════════════════════════════

def sync_memory() -> dict:
    """Read local memory files and produce a sync manifest for KG operations."""
    if not MEMORY_DIR.exists():
        return {"status": "no_memory_dir", "entries": []}

    manifest = []
    for md_file in MEMORY_DIR.rglob("*.md"):
        if md_file.name in ("MEMORY.md",):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            entry = parse_memory_frontmatter(content, str(md_file.relative_to(MEMORY_DIR)))
            if entry:
                manifest.append(entry)
        except Exception:
            pass

    return {
        "status": "ok",
        "total": len(manifest),
        "entries": manifest,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def parse_memory_frontmatter(content: str, rel_path: str) -> Optional[dict]:
    """Extract YAML-like frontmatter from memory file."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None

    end_idx = -1
    for i in range(1, min(len(lines), 30)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx < 0:
        return None

    meta = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    body_start = end_idx + 1
    body = "\n".join(lines[body_start:]).strip()

    return {
        "rel_path": rel_path,
        "atomic_id": meta.get("atomic_id", ""),
        "name": meta.get("name", ""),
        "type": meta.get("type", ""),
        "domain": meta.get("domain", ""),
        "confidence": meta.get("confidence", ""),
        "superseded_by": meta.get("superseded_by", ""),
        "body_preview": body[:200],
    }


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: adapter-bridge.py <command> [args...]")
        print("Commands: state, inject, route, health, sync-memory, serve")
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "state":
            state = load_bridge_state()
            state["health"] = get_health()
            print(json.dumps(state, indent=2, ensure_ascii=False))

        elif cmd == "inject":
            key = sys.argv[2] if len(sys.argv) > 2 else "all"
            result = inject(key)
            if result:
                print(result)

        elif cmd == "route":
            event = sys.argv[2] if len(sys.argv) > 2 else "Unknown"
            payload = sys.argv[3] if len(sys.argv) > 3 else None
            print(json.dumps(route_event(event, payload), indent=2, ensure_ascii=False))

        elif cmd == "health":
            print(json.dumps(get_health(), indent=2, ensure_ascii=False))

        elif cmd == "sync-memory":
            print(json.dumps(sync_memory(), indent=2, ensure_ascii=False))

        elif cmd == "serve":
            serve_daemon()

        else:
            print(f"Unknown command: {cmd}")
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
        sys.exit(1)


def serve_daemon():
    """Daemon mode: read JSON lines from stdin, write JSON lines to stdout."""
    print(json.dumps({"status": "ready", "pid": os.getpid()}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("command", "")
            args = req.get("args", [])

            if cmd == "inject":
                result = inject(args[0] if args else "all")
                print(json.dumps({"ok": True, "result": result}), flush=True)
            elif cmd == "health":
                print(json.dumps({"ok": True, "result": get_health()}), flush=True)
            elif cmd == "route":
                print(json.dumps({"ok": True, "result": route_event(args[0] if args else "Unknown")}), flush=True)
            elif cmd == "sync-memory":
                print(json.dumps({"ok": True, "result": sync_memory()}), flush=True)
            elif cmd == "quit":
                print(json.dumps({"ok": True, "status": "exiting"}), flush=True)
                break
            else:
                print(json.dumps({"ok": False, "error": f"Unknown command: {cmd}"}), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "Invalid JSON"}), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
