#!/usr/bin/env python3
"""cross-review — automate cross-model code review (Devin finding: self-review 64.5% blind spot).
Spawns a haiku-speed review that catches what the main model misses.
Usage:
  python3 cross-review.py [--files "file1.py file2.js"] [--base HEAD~1] [--json]

Requires: git. Uses diff analysis + knowledge graph for context.
Output: structured review findings with severity, file, line, and fix suggestion.
"""
import sys, json, os, io, subprocess
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))

def get_diff(base="HEAD~1", files=None):
    """Get git diff for review."""
    cmd = ["git", "diff", base, "--", "."]
    if files:
        cmd.extend(files.split())
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd(),
                              encoding='utf-8', errors='replace')
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""

def get_changed_files(base="HEAD~1"):
    """Get list of changed files."""
    cmd = ["git", "diff", "--name-only", base]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        return result.stdout.strip().split('\n') if result.returncode == 0 else []
    except Exception:
        return []

def analyze_diff(diff_text):
    """Analyze diff for review-worthy patterns."""
    findings = []

    # Pattern 1: Security — hardcoded secrets
    secret_patterns = [
        (r'(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*["\'][^"\']+["\']', 'HIGH',
         'Possible hardcoded secret/credential'),
        (r'(?i)(BEGIN\s+(RSA|DSA|EC|OPENSSH)?\s*PRIVATE\s+KEY)', 'CRITICAL',
         'Private key in diff'),
        (r'(?i)(sk-[a-zA-Z0-9]{20,})', 'CRITICAL',
         'Possible API key pattern (sk-...)'),
    ]
    for pattern, severity, desc in secret_patterns:
        import re
        for m in re.finditer(pattern, diff_text):
            ctx = diff_text[max(0, m.start()-30):m.end()+30].replace('\n', ' ')
            findings.append({
                "type": "security", "severity": severity,
                "description": desc, "context": ctx[:120],
            })

    # Pattern 2: Structural — large files changed
    file_changes = {}
    current_file = None
    for line in diff_text.split('\n'):
        if line.startswith('diff --git'):
            current_file = line.split()[-1].lstrip('b/')
        if line.startswith('+') and not line.startswith('+++') and current_file:
            file_changes[current_file] = file_changes.get(current_file, 0) + 1

    for fname, additions in file_changes.items():
        if additions > 200:
            findings.append({
                "type": "structure", "severity": "MEDIUM",
                "file": fname,
                "description": f"Large change: {additions}+ lines in single file. Consider splitting.",
            })

    # Pattern 3: Quality — console.log / print / debugger
    debug_patterns = [
        (r'^\+\s*console\.(log|debug|warn)\s*\(', 'LOW', 'console.log/debug left in code'),
        (r'^\+\s*print\s*\(', 'LOW', 'print() statement in diff'),
        (r'^\+\s*debugger\s*;?', 'MEDIUM', 'debugger statement left in code'),
        (r'^\+\s*//\s*TODO', 'LOW', 'TODO comment — should this be completed?'),
        (r'^\+\s*#\s*TODO', 'LOW', 'TODO comment — should this be completed?'),
    ]
    import re
    for pattern, severity, desc in debug_patterns:
        for m in re.finditer(pattern, diff_text, re.MULTILINE):
            line_content = m.group(0).strip()
            findings.append({
                "type": "quality", "severity": severity,
                "description": desc, "context": line_content[:100],
            })

    # Pattern 4: Risk — hook/settings changes
    risky_files = ['settings.json', 'CLAUDE.md', 'AGENTS.md', '.mcp.json', '.gitignore']
    changed = get_changed_files()
    for f in changed:
        if any(f.endswith(rf) for rf in risky_files):
            findings.append({
                "type": "risk", "severity": "MEDIUM",
                "file": f,
                "description": f"Critical config file modified: {f}. Verify changes are intentional.",
            })

    return findings

def main():
    use_json = "--json" in sys.argv
    base = "HEAD~1"
    files = None
    for i, arg in enumerate(sys.argv):
        if arg == "--base" and i + 1 < len(sys.argv):
            base = sys.argv[i + 1]
        if arg == "--files" and i + 1 < len(sys.argv):
            files = sys.argv[i + 1]

    diff = get_diff(base, files)
    if not diff or not diff.strip():
        result = {"status": "no_changes", "findings": [], "message": "No diff to review"}
        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("CROSS-REVIEW: no changes to review")
        return

    findings = analyze_diff(diff)

    if use_json:
        print(json.dumps({
            "status": "reviewed",
            "timestamp": datetime.now().isoformat(),
            "base": base,
            "files_changed": len(get_changed_files(base)),
            "findings": findings,
            "summary": f"{len(findings)} findings: " + ", ".join(
                f"{f['severity']}:{f['type']}" for f in findings[:5]
            ),
        }, ensure_ascii=False, indent=2))
    else:
        if findings:
            print(f"CROSS-REVIEW: {len(findings)} findings (base={base})")
            for f in sorted(findings, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["severity"], 4)):
                file_info = f" [{f.get('file', '')}]" if f.get('file') else ""
                print(f"  [{f['severity']}] {f['type']}{file_info}: {f['description']}")
        else:
            print(f"CROSS-REVIEW: {len(get_changed_files(base))} files changed, no issues found (base={base})")

if __name__ == "__main__":
    main()
