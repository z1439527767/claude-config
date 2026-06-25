#!/usr/bin/env python3
"""adapter-validate — check all scripts for standardized interface conventions.
OpenHands-inspired: every tool should have discoverable inputs, outputs, and exit codes.

Usage:
  python adapter-validate.py              # Human-readable report
  python adapter-validate.py --json        # Machine-readable
  python adapter-validate.py --fix          # Auto-fix simple issues (add help stubs)
"""

import sys, json, io, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = HOME / "scripts"
HOOKS_DIR = SCRIPTS_DIR / "hooks"
LIB_DIR = SCRIPTS_DIR / "lib"

# Standard interface requirements (per script type)
CHECKS = {
    "help": {
        "description": "Has --help / -h / help text (docstring or param block)",
        "severity": "WARN",
        "ps1_patterns": [r"<#", r"\.SYNOPSIS", r"Write-Output.*usage", r"param\s*\("],
        "py_patterns": [r'"""', r"__doc__", r"[-][-]help", r"print.*[Uu]sage"],
    },
    "exit_codes": {
        "description": "Uses exit codes (exit 0 for success, non-zero for failure)",
        "severity": "WARN",
        "ps1_patterns": [r"exit\s+\d+"],
        "py_patterns": [r"sys\.exit\s*\(\s*\d+\s*\)"],
    },
    "error_handling": {
        "description": "Has error handling (try/catch in PS, try/except in Python)",
        "severity": "INFO",
        "ps1_patterns": [r"try\s*\{", r"catch\s*\{", r"-ErrorAction\s+(Stop|Continue)"],
        "py_patterns": [r"try\s*:", r"except\s+", r"except\s*\w+Error"],
    },
    "encoding": {
        "description": "Handles UTF-8 encoding (Console OutputEncoding in PS, io.TextIOWrapper in Py)",
        "severity": "INFO",
        "ps1_patterns": [r"\[Console\]::OutputEncoding\s*=", r"\[Text\.Encoding\]::UTF8"],
        "py_patterns": [r"io\.TextIOWrapper", r"encoding\s*=\s*['\"]utf-8['\"]"],
    },
    "perf_logging": {
        "description": "PS1 scripts use Write-PerfLog for hook performance tracking",
        "severity": "INFO",
        "ps1_patterns": [r"Write-PerfLog"],
        "py_patterns": [],  # Python scripts don't need perf logging
    },
}

# Expected exit code conventions
EXIT_CODE_DOC = {
    0: "Success",
    1: "Warnings / non-critical issues",
    2: "Errors found",
    3: "Critical failure",
}


def check_ps1(filepath: Path) -> dict:
    """Check a PowerShell script against interface standards."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"file": filepath.name, "type": "ps1", "error": "Cannot read file"}

    lines = content.count("\n") + 1
    results = {"file": filepath.name, "type": "ps1", "lines": lines, "checks": {}}

    for check_name, check_config in CHECKS.items():
        patterns = check_config.get("ps1_patterns", [])
        if not patterns:
            results["checks"][check_name] = {"pass": True, "note": "N/A for PS1"}
            continue
        passed = any(re.search(p, content, re.IGNORECASE | re.MULTILINE) for p in patterns)
        results["checks"][check_name] = {
            "pass": passed,
            "severity": check_config["severity"],
            "description": check_config["description"],
        }

    return results


def check_py(filepath: Path) -> dict:
    """Check a Python script against interface standards."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"file": filepath.name, "type": "py", "error": "Cannot read file"}

    lines = content.count("\n") + 1
    results = {"file": filepath.name, "type": "py", "lines": lines, "checks": {}}

    for check_name, check_config in CHECKS.items():
        patterns = check_config.get("py_patterns", [])
        if not patterns:
            results["checks"][check_name] = {"pass": True, "note": "N/A for Python"}
            continue
        passed = any(re.search(p, content, re.IGNORECASE | re.MULTILINE) for p in patterns)
        results["checks"][check_name] = {
            "pass": passed,
            "severity": check_config["severity"],
            "description": check_config["description"],
        }

    return results


def scan_all() -> list[dict]:
    """Scan all scripts and return check results."""
    results = []

    for directory, _label in [(HOOKS_DIR, "hooks"), (LIB_DIR, "lib"), (SCRIPTS_DIR, "scripts")]:
        if not directory.exists():
            continue
        for f in sorted(directory.rglob("*")):
            if f.suffix == ".ps1":
                results.append(check_ps1(f))
            elif f.suffix == ".py":
                results.append(check_py(f))

    return results


def compute_score(results: list[dict]) -> dict:
    """Compute compliance score across all scripts."""
    total_checks = 0
    passed_checks = 0
    by_check = defaultdict(lambda: {"total": 0, "passed": 0})

    for r in results:
        for check_name, check_result in r.get("checks", {}).items():
            total_checks += 1
            by_check[check_name]["total"] += 1
            if check_result.get("pass"):
                passed_checks += 1
                by_check[check_name]["passed"] += 1

    score = passed_checks / max(total_checks, 1)

    return {
        "score": round(score, 3),
        "total_checks": total_checks,
        "passed": passed_checks,
        "failed": total_checks - passed_checks,
        "by_check": {k: {"passed": v["passed"], "total": v["total"],
                          "rate": round(v["passed"] / max(v["total"], 1), 2)}
                      for k, v in sorted(by_check.items())},
    }


def auto_fix(results: list[dict]) -> int:
    """Auto-fix simple issues (add help stubs to scripts without them)."""
    fixed = 0
    for r in results:
        checks = r.get("checks", {})
        if checks.get("help", {}).get("pass"):
            continue

        filepath = None
        for d in [HOOKS_DIR, LIB_DIR, SCRIPTS_DIR]:
            candidate = d / r["file"]
            if candidate.exists():
                filepath = candidate
                break

        if not filepath:
            continue

        content = filepath.read_text(encoding="utf-8", errors="ignore")
        if r["type"] == "ps1":
            stub = f"<#\n.SYNOPSIS\n{r['file']} — (add description)\n#>\n"
            if "<#" not in content:
                filepath.write_text(stub + content, encoding="utf-8")
                fixed += 1
        elif r["type"] == "py":
            stub = f'"""(add description)"""\n'
            if '"""' not in content.split("\n", 5)[0] and "'''" not in content.split("\n", 5)[0]:
                filepath.write_text(stub + content, encoding="utf-8")
                fixed += 1

    return fixed


def main():
    use_json = "--json" in sys.argv
    do_fix = "--fix" in sys.argv
    fixed = 0

    results = scan_all()
    score = compute_score(results)

    if do_fix:
        fixed = auto_fix(results)
        if fixed:
            results = scan_all()  # re-scan
            score = compute_score(results)

    if use_json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "files": results,
            "fixed_count": fixed if do_fix else 0,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════╗")
        print(f"║  Script Interface Compliance Report  ║")
        print(f"╠══════════════════════════════════════╣")
        print(f"║  Score: {score['score']:.0%}  ({score['passed']}/{score['total_checks']} checks passed)  ║")
        print(f"║  Files: {len(results)} scripts scanned        ║")
        print(f"╚══════════════════════════════════════╝")
        print()

        # By check type
        print("  ── Check Type Summary ──")
        for check_name, stats in score["by_check"].items():
            icon = "✅" if stats["rate"] >= 0.8 else "⚠️" if stats["rate"] >= 0.5 else "🔴"
            print(f"  {icon} {check_name}: {stats['passed']}/{stats['total']} ({stats['rate']:.0%})")
        print()

        # Files with issues
        issues = [r for r in results if not all(c.get("pass", True) for c in r.get("checks", {}).values())]
        if issues:
            print(f"  ── {len(issues)} Scripts with Issues ──")
            for r in issues:
                failed = [k for k, v in r.get("checks", {}).items() if not v.get("pass")]
                print(f"  🔧 {r['file']}: missing {', '.join(failed)}")
        else:
            print(f"  ✅ All scripts pass all interface checks!")

        if do_fix:
            print(f"\n  Auto-fix: {fixed} help stubs added")

    sys.exit(0 if score["score"] >= 0.7 else 1)


if __name__ == "__main__":
    main()
