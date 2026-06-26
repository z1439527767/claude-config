#!/usr/bin/env python3
"""
adapter-dashboard.py — Rich terminal dashboard for .claude framework.
Replaces bare health-check.py with multi-layer system overview.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(os.environ.get("USERPROFILE", "~")) / ".claude"
SCRIPTS_DIR = BASE_DIR / "scripts"

# Terminal colors (ANSI)
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}


def ok(s: str) -> str:
    return f"{C['green']}{s}{C['reset']}"


def warn(s: str) -> str:
    return f"{C['yellow']}{s}{C['reset']}"


def err(s: str) -> str:
    return f"{C['red']}{s}{C['reset']}"


def hdr(s: str) -> str:
    return f"{C['bold']}{C['cyan']}{s}{C['reset']}"


def dim(s: str) -> str:
    return f"{C['dim']}{s}{C['reset']}"


def run_ps(path: str, args: str = "") -> str:
    """Run a PowerShell script and return stdout."""
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path] +
            (args.split() if args else []),
            capture_output=True, text=True, timeout=30, cwd=str(BASE_DIR)
        )
        return result.stdout.strip() or result.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"


def run_py(path: str, args: str = "") -> str:
    """Run a Python script and return stdout."""
    try:
        result = subprocess.run(
            ["python", path] + (args.split() if args else []),
            capture_output=True, text=True, timeout=10, cwd=str(BASE_DIR)
        )
        return result.stdout.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"


def get_git_status() -> dict:
    try:
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "log", "--oneline", "-5"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        return {
            "last_5": [l[:80] for l in lines if l],
            "branch": "master",
        }
    except Exception:
        return {"last_5": [], "branch": "unknown"}


def get_file_count(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.rglob(pattern)))


def main():
    print(f"\n{C['bold']}═══ .CLAUDE FRAMEWORK DASHBOARD {datetime.now().strftime('%H:%M:%S')} ═══{C['reset']}\n")

    # ── Layer 0: Health ──
    print(hdr("▸ L0 HEALTH"))
    health_out = run_py(str(SCRIPTS_DIR / "health-check.py"))
    health_lines = [l.strip() for l in health_out.split("\n") if l.strip()]
    for line in health_lines[:8]:
        if "OK" in line:
            print(f"  {ok(line)}")
        elif any(w in line.lower() for w in ["error", "fail", "issue"]):
            print(f"  {err(line)}")
        else:
            print(f"  {dim(line)}")
    print()

    # ── Layer 1: Files ──
    print(hdr("▸ L1 FILES"))
    hooks = get_file_count(BASE_DIR / "scripts" / "hooks", "*.ps1")
    libs = get_file_count(BASE_DIR / "scripts" / "lib", "*.ps1")
    py_files = get_file_count(SCRIPTS_DIR, "*.py")
    rules = get_file_count(BASE_DIR / ".claude" / "rules", "*.md")
    skills = get_file_count(BASE_DIR / ".claude" / "skills", "**/SKILL.md")

    print(f"  Hooks:    {hooks} ps1    Lib: {libs} ps1")
    print(f"  Python:   {py_files} scripts")
    print(f"  Rules:    {rules} md      Skills: {skills}")
    print()

    # ── Layer 2: Git ──
    print(hdr("▸ L2 GIT"))
    git = get_git_status()
    for i, commit in enumerate(git["last_5"]):
        prefix = "→" if i == 0 else " "
        print(f"  {dim(prefix)} {commit}")
    print()

    # ── Layer 3: Memory ──
    print(hdr("▸ L3 MEMORY"))
    mem_dir = BASE_DIR / "projects" / f"C--Users-{os.environ.get("USERNAME","z1439")}--claude" / "memory"
    mem_files = get_file_count(mem_dir, "*.md") - 1  # exclude MEMORY.md itself
    mem_index = mem_dir / "MEMORY.md"
    indexed = 0
    if mem_index.exists():
        indexed = len([l for l in mem_index.read_text(encoding="utf-8").split("\n") if l.startswith("- [")])

    mem_tree = mem_dir / "tree.json"
    tree_age = "N/A"
    if mem_tree.exists():
        try:
            tree = json.loads(mem_tree.read_text())
            age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(tree["updated"])).total_seconds() / 3600
            tree_age = f"{age_h:.1f}h"
        except Exception:
            tree_age = "broken"

    freshness = ok("all fresh") if indexed == mem_files else warn(f"{indexed}/{mem_files} indexed")
    print(f"  Files: {mem_files} md    Indexed: {indexed}")
    print(f"  Tree:  {tree_age} old    Freshness: {freshness}")
    print()

    # ── Layer 4: Evolution ──
    print(hdr("▸ L4 EVOLUTION"))
    evo_log = BASE_DIR / ".claude" / "evolution_log.jsonl"
    if evo_log.exists():
        lines = [l for l in evo_log.read_text(encoding="utf-8").split("\n") if l.strip()]
        total = len(lines)
        last_entry = {}
        if lines:
            try:
                last_entry = json.loads(lines[-1])
            except Exception:
                pass
        last_time = last_entry.get("timestamp", "unknown")[:19] if last_entry else "N/A"
        last_changes = last_entry.get("changes", []) if last_entry else []
        l3_count = sum(1 for c in last_changes if "L3" in str(c))

        print(f"  Total:   {total} cycles")
        print(f"  Last:    {last_time} ({len(last_changes)} changes, {l3_count} L3)")
    else:
        print(f"  {dim('No evolution log yet')}")
    print()

    # ── Layer 5: MCP ──
    print(hdr("▸ L5 MCP SERVERS"))
    mcp_out = run_ps(str(SCRIPTS_DIR / "adapter-mcp.ps1"), "-Stats")
    for line in mcp_out.split("\n")[:6]:
        print(f"  {dim(line)}")
    print()

    # ── Summary ──
    print(hdr("▸ ACTIONS"))
    adapter_state = run_ps(str(SCRIPTS_DIR / "adapter-state.ps1"), "-Brief")
    print(f"  {adapter_state}")

    # Quick checks
    halt_file = BASE_DIR / ".claude" / "HALT"
    if halt_file.exists():
        print(f"  {err('⚠ HALT FILE EXISTS — autonomous loop paused')}")

    evo_gate = BASE_DIR / ".claude" / "evo_gate.json"
    if evo_gate.exists():
        try:
            gate = json.loads(evo_gate.read_text())
            recent = len([t for t in gate.get("recent_evo_timestamps", []) if True])
            if recent >= 10:
                print(f"  {warn(f'⚠ Evolution gated ({recent} in 7 days)')}")
        except Exception:
            pass

    print(f"\n{C['dim']}Dashboard complete. Use adapter-*.ps1 tools for detailed views.{C['reset']}\n")


if __name__ == "__main__":
    main()
