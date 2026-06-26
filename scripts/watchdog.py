#!/usr/bin/env python3
"""watchdog — file system watcher for key .claude directories.
Triggers actions when files change: auto-verify on config changes, log events.
Usage:
  python3 watchdog.py                     # Watch default directories
  python3 watchdog.py --once              # Check once and report
  python3 watchdog.py --daemon 60         # Watch every 60 seconds (polling mode)

Watches:
  - .claude/settings.json          → auto-verify on change
  - .claude/CLAUDE.md              → auto-verify on change
  - .claude/.claude/rules/         → rule auditor on change
  - .claude/scripts/hooks/         → syntax check on change
  - .claude/session-env/           → monitor circuit breaker state
"""
import sys, json, os, io, time, hashlib, subprocess
from pathlib import Path
from datetime import datetime
try: from db import write_log
except ImportError: write_log = lambda s,k,d: None

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
SCRIPTS = CLAUDE / 'scripts'
STATE_FILE = CLAUDE / '.claude' / 'watchdog_state.json'
EVENT_LOG = CLAUDE / '.claude' / 'watchdog_events.jsonl'

WATCH_TARGETS = [
    {
        "path": str(CLAUDE / 'settings.json'),
        "label": "settings.json",
        "on_change": "verify",
        "description": "Agent configuration",
    },
    {
        "path": str(CLAUDE / 'CLAUDE.md'),
        "label": "CLAUDE.md",
        "on_change": "verify_refs",
        "description": "Main agent instructions",
    },
    {
        "path": str(CLAUDE / '.claude' / 'rules'),
        "label": "rules/",
        "on_change": "audit_rules",
        "description": "Behavioral rules directory",
    },
    {
        "path": str(CLAUDE / 'scripts' / 'hooks'),
        "label": "hooks/",
        "on_change": "syntax_check",
        "description": "Hook scripts directory",
    },
    {
        "path": str(CLAUDE / 'scripts' / 'lib'),
        "label": "lib/",
        "on_change": "syntax_check",
        "description": "Library scripts directory",
    },
]

def hash_file(filepath):
    """SHA256 hash of a file."""
    try:
        return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()
    except Exception:
        return None

def hash_directory(dirpath):
    """Combined hash of all files in a directory."""
    try:
        hasher = hashlib.sha256()
        for f in sorted(Path(dirpath).rglob('*')):
            if f.is_file():
                hasher.update(f.read_bytes())
                hasher.update(str(f.relative_to(dirpath)).encode())
        return hasher.hexdigest()
    except Exception:
        return None

def load_state():
    """Load previous file hashes."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"hashes": {}, "last_check": None}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def log_event(event_type, target, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "target": target,
        "detail": detail,
    }
    try:
        write_log("watchdog_events", None, entry)
    except Exception:
        EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(EVENT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def run_action(action, target_label):
    """Run the appropriate action for a changed target."""
    actions = {
        "verify": ["python", str(SCRIPTS / "verify-all.py"), "--quick"],
        "verify_refs": ["python", str(SCRIPTS / "verify-all.py"), "--quick"],
        "audit_rules": ["python", str(SCRIPTS / "rule-auditor.py")],
        "syntax_check": ["python", str(SCRIPTS / "verify-all.py"), "--quick"],
    }

    if action not in actions:
        return

    try:
        result = subprocess.run(
            actions[action], capture_output=True, text=True, timeout=30,
            encoding='utf-8', errors='replace'
        )
        log_event("action_ran", target_label, f"action={action} rc={result.returncode}")
    except Exception as e:
        log_event("action_error", target_label, str(e))

def check_once():
    """One-time check for changes."""
    state = load_state()
    changes = []
    now = datetime.now()

    for target in WATCH_TARGETS:
        path = target["path"]
        label = target["label"]

        if os.path.isfile(path):
            current_hash = hash_file(path)
        elif os.path.isdir(path):
            current_hash = hash_directory(path)
        else:
            continue

        if current_hash is None:
            continue

        old_hash = state["hashes"].get(label)
        state["hashes"][label] = current_hash

        if old_hash and old_hash != current_hash:
            changes.append(target)
            log_event("changed", label, f"old={old_hash[:12]} new={current_hash[:12]}")

    state["last_check"] = now.isoformat()
    save_state(state)

    if changes:
        print(f"WATCHDOG: {len(changes)} changes detected")
        for t in changes:
            print(f"  → {t['label']}: {t['description']}")
            if t.get("on_change"):
                print(f"    running: {t['on_change']}")
                run_action(t["on_change"], t["label"])
    else:
        print("WATCHDOG: no changes detected")

def daemon_mode(interval):
    """Polling-based daemon mode."""
    print(f"WATCHDOG: daemon mode, polling every {interval}s. Ctrl+C to stop.")
    try:
        while True:
            check_once()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWATCHDOG: stopped.")

def main():
    if "--once" in sys.argv:
        check_once()
    elif "--init" in sys.argv:
        state = load_state()
        for target in WATCH_TARGETS:
            path = target["path"]
            if os.path.isfile(path):
                state["hashes"][target["label"]] = hash_file(path)
            elif os.path.isdir(path):
                state["hashes"][target["label"]] = hash_directory(path)
        save_state(state)
        print("WATCHDOG: initialized hashes for all targets")
    elif "--daemon" in sys.argv:
        interval = 60
        for i, arg in enumerate(sys.argv):
            if arg == "--daemon" and i + 1 < len(sys.argv):
                interval = int(sys.argv[i + 1])
        daemon_mode(interval)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
