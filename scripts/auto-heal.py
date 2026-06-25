#!/usr/bin/env python3
"""auto-heal — autonomous self-repair loop.
Runs verify-all, parses findings, auto-fixes safe issues, commits repairs.
Usage:
  python3 auto-heal.py                    # Run once: detect + fix + report
  python3 auto-heal.py --dry-run          # Detect only, don't fix
  python3 auto-heal.py --daemon 300       # Run every 300 seconds (background)
  python3 auto-heal.py --commit           # Auto-commit fixes (requires --fix)

Safe auto-fixes (no risk):
  - Add missing YAML frontmatter to rule files
  - Fix broken script refs in CLAUDE.md/AGENTS.md
  - Remove empty session directories
  - Clear stale lock files
  - Update memory scores (run memory-score.ps1)

Unsafe (requires --commit):
  - Git add + commit fixes
"""
import sys, json, os, io, re, subprocess, time
from pathlib import Path
from datetime import datetime
try: from db import write_log
except ImportError: write_log = lambda s,k,d: None

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
SCRIPTS = CLAUDE / 'scripts'
RULES_DIR = CLAUDE / '.claude' / 'rules'
HEAL_LOG = CLAUDE / '.claude' / 'auto_heal_log.jsonl'

def log_heal(action, target, result, detail=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "target": target,
        "result": result,
        "detail": detail,
    }
    try:
        write_log("auto_heal", None, entry)
    except Exception:
        HEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HEAL_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def run_verify():
    """Run verify-all and return parsed results."""
    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "verify-all.py"), "--json"],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', errors='replace'
        )
        if result.returncode in (0, 1, 2):
            return json.loads(result.stdout)
    except Exception as e:
        print(f"auto-heal: verify-all failed: {e}")
    return None

def fix_missing_frontmatter(findings):
    """Add YAML frontmatter to rules that lack it."""
    fixed = 0
    for f in findings:
        if "Missing YAML frontmatter" in f.get("message", ""):
            rule_file = RULES_DIR / f["component"]
            if rule_file.exists():
                content = rule_file.read_text(encoding='utf-8')
                if not content.startswith('---'):
                    fm = f"---\nmode: always\ndescription: {f['component'].replace('.md','')} rules\n---\n\n"
                    rule_file.write_text(fm + content, encoding='utf-8')
                    log_heal("add_frontmatter", f["component"], "fixed")
                    fixed += 1
    return fixed

def fix_broken_refs(findings, claude_md_path=None):
    """Fix broken script references in config files."""
    if claude_md_path is None:
        claude_md_path = CLAUDE / 'CLAUDE.md'
    if not claude_md_path.exists():
        return 0

    fixed = 0
    content = claude_md_path.read_text(encoding='utf-8')

    for f in findings:
        if "Broken script ref" in f.get("message", ""):
            # Extract the broken path and try to find the correct one
            broken = f.get("message", "").split(": ")[-1].strip()
            if not broken:
                continue

            # Search for the actual file
            filename = Path(broken).name
            candidates = list(SCRIPTS.rglob(filename))
            if len(candidates) == 1:
                correct = str(candidates[0].relative_to(CLAUDE)).replace('\\', '/')
                if broken != correct:
                    content = content.replace(broken, correct)
                    log_heal("fix_ref", broken, "fixed", f"→ {correct}")
                    fixed += 1

    if fixed:
        claude_md_path.write_text(content, encoding='utf-8')

    return fixed

def clean_empty_dirs():
    """Remove empty session directories."""
    session_dir = CLAUDE / 'session-env'
    if not session_dir.exists():
        return 0
    cleaned = 0
    for d in list(session_dir.iterdir()):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
                log_heal("clean_empty_dir", str(d.relative_to(CLAUDE)), "removed")
                cleaned += 1
            except Exception:
                pass
    return cleaned

def clear_stale_locks():
    """Remove stale lock files (>30 min old)."""
    lock_files = list((CLAUDE / '.claude').glob('*.lock'))
    cleaned = 0
    for lf in lock_files:
        try:
            age = (datetime.now() - datetime.fromtimestamp(lf.stat().st_mtime)).total_seconds()
            if age > 1800:  # 30 min
                lf.unlink()
                log_heal("clear_lock", str(lf.relative_to(CLAUDE)), "removed", f"age={age:.0f}s")
                cleaned += 1
        except Exception:
            pass
    return cleaned

def run_memory_scoring():
    """Run memory-score.ps1 to update Ebbinghaus scores."""
    score_script = SCRIPTS / 'hooks' / 'memory-score.ps1'
    if not score_script.exists():
        return False
    try:
        result = subprocess.run(
            ["pwsh", "-ExecutionPolicy", "Bypass", "-File", str(score_script),
             "-RecordAccess:$false"],
            capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        return result.returncode == 0
    except Exception:
        return False

def auto_commit():
    """Commit fixes with standardized message."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=CLAUDE, capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m",
             "auto-heal: automated fixes\n\nCo-Authored-By: Claude <noreply@anthropic.com>"],
            cwd=CLAUDE, capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        return result.returncode == 0
    except Exception:
        return False

def heal(dry_run=False, commit=False):
    """Main heal cycle."""
    print(f"AUTO-HEAL: starting at {datetime.now().isoformat()}")
    results = {"fixed": 0, "actions": []}

    # Step 1: Run verification
    data = run_verify()
    if not data:
        print("AUTO-HEAL: verification failed, aborting")
        return results

    findings = data.get("findings", [])
    errors = [f for f in findings if f["severity"] in ("ERROR", "CRITICAL")]
    warns = [f for f in findings if f["severity"] == "WARN"]

    print(f"AUTO-HEAL: {len(errors)} errors, {len(warns)} warnings found")

    if dry_run:
        for f in errors + warns:
            print(f"  [{f['severity']}] {f['component']}: {f['message']}")
            if f.get("auto_fix"):
                print(f"    would fix: {f['auto_fix']}")
        return results

    # Step 2: Apply fixes
    # Fix 1: Missing frontmatter
    n = fix_missing_frontmatter(findings)
    if n:
        print(f"AUTO-HEAL: fixed {n} missing frontmatter")
        results["fixed"] += n
        results["actions"].append(f"frontmatter: {n}")

    # Fix 2: Broken references
    n = fix_broken_refs(findings)
    if n:
        print(f"AUTO-HEAL: fixed {n} broken refs")
        results["fixed"] += n
        results["actions"].append(f"broken_refs: {n}")

    # Fix 3: Empty directories
    n = clean_empty_dirs()
    if n:
        print(f"AUTO-HEAL: cleaned {n} empty dirs")
        results["fixed"] += n
        results["actions"].append(f"empty_dirs: {n}")

    # Fix 4: Stale locks
    n = clear_stale_locks()
    if n:
        print(f"AUTO-HEAL: cleared {n} stale locks")
        results["fixed"] += n
        results["actions"].append(f"stale_locks: {n}")

    # Fix 5: Memory scoring
    if run_memory_scoring():
        results["actions"].append("memory_scored")

    # Step 3: Optional commit
    if commit and results["fixed"] > 0:
        if auto_commit():
            print("AUTO-HEAL: committed fixes")
            results["actions"].append("committed")

    print(f"AUTO-HEAL: done — {results['fixed']} fixes applied: {', '.join(results['actions'])}")
    return results

def daemon_mode(interval):
    """Run continuously at specified interval."""
    print(f"AUTO-HEAL: daemon mode, interval={interval}s. Ctrl+C to stop.")
    try:
        while True:
            heal()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nAUTO-HEAL: daemon stopped.")

def main():
    dry_run = "--dry-run" in sys.argv
    commit = "--commit" in sys.argv
    daemon = None

    for i, arg in enumerate(sys.argv):
        if arg == "--daemon" and i + 1 < len(sys.argv):
            daemon = int(sys.argv[i + 1])

    if daemon:
        daemon_mode(daemon)
    else:
        heal(dry_run=dry_run, commit=commit)

if __name__ == "__main__":
    main()
