#!/usr/bin/env python3
"""rule-auditor — Prune rules with the 4-question Rubric + detect stale/oversized/duplicate.
Usage:
  python3 rule-auditor.py              # Audit all rules
  python3 rule-auditor.py --json       # Machine-readable output
  python3 rule-auditor.py --prune-dry  # Show which rules would be pruned

Rubric (from production consensus):
  1. Failure-backed? — Would agent make mistake without this rule?
  2. Tool-enforceable? — Can this be a lint/hook/test instead?
  3. Decision-encoding? — Does it encode a key decision?
  4. Triggerable? — Does it have clear trigger conditions?

Score 0-4. Rules scoring 0-1 are candidates for deletion.
"""
import sys, json, os, re, io
from pathlib import Path
from datetime import datetime

# Fix UnicodeEncodeError on Windows (emoji in output)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
RULES_DIR = HOME / '.claude' / '.claude' / 'rules'

def parse_frontmatter(content):
    """Extract YAML frontmatter if present."""
    if not content.startswith('---'):
        return {}, content
    end = content.find('---', 3)
    if end == -1:
        return {}, content
    fm = {}
    for line in content[3:end].strip().split('\n'):
        line = line.strip()
        if ':' in line:
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip()
    return fm, content[end+3:]

def analyze_rule(filepath):
    """Analyze a single rule file."""
    content = filepath.read_text(encoding='utf-8', errors='ignore')
    fm, body = parse_frontmatter(content)
    lines = content.count('\n') + 1

    result = {
        "file": filepath.name,
        "path": str(filepath.relative_to(HOME)),
        "lines": lines,
        "has_frontmatter": bool(fm),
        "mode": fm.get("mode", "unspecified"),
        "source": fm.get("source", ""),
        "oversized": lines > 200,
        "stale": False,  # Requires git history check
    }

    # Heuristic rubric scores
    scores = {"failure_backed": 0, "tool_enforceable": 0, "decision_encoding": 0, "triggerable": 0}

    # Has imperative rules (suggests failure-backed)
    if re.search(r'(?m)^[-\*\d]\.\s+\*\*', body):  # Has bold imperative items
        scores["failure_backed"] = 1
    if re.search(r'(?m)^> 🔴 Must', body):  # Critical priority marker
        scores["failure_backed"] = 1

    # Could be tool-enforceable (mentions hooks/scripts/lint)
    if re.search(r'hook|script|lint|prettier|eslint|ruff|test|validate', body, re.I):
        scores["tool_enforceable"] = 1

    # Encodes decisions (mentions specific choices)
    if re.search(r'选[用择]|选择|decision|choose|prefer|优先|allow|deny|禁止|never|always', body, re.I):
        scores["decision_encoding"] = 1

    # Has trigger conditions (globs, specific files, specific scenarios)
    if fm.get("globs") or fm.get("paths") or re.search(r'(?m)^[-\*]\s+(当|遇到|if|when|before|after)', body, re.I):
        scores["triggerable"] = 1
    if fm.get("mode") == "manual":
        scores["triggerable"] = 1  # Manually triggered = clear trigger

    result["rubric"] = scores
    result["rubric_score"] = sum(scores.values())
    result["recommendation"] = (
        "keep" if result["rubric_score"] >= 3 else
        "review" if result["rubric_score"] == 2 else
        "prune_candidate"
    )

    return result

def main():
    if not RULES_DIR.exists():
        print(f"Rules directory not found: {RULES_DIR}")
        return

    rules = []
    for f in sorted(RULES_DIR.glob("*.md")):
        if f.name == "core.md":
            continue  # Core invariants, never pruned
        rules.append(analyze_rule(f))

    rules.sort(key=lambda r: r["rubric_score"])

    use_json = "--json" in sys.argv
    prune_dry = "--prune-dry" in sys.argv

    if use_json:
        print(json.dumps({
            "audited_at": datetime.now().isoformat(),
            "total_rules": len(rules),
            "oversized": [r["file"] for r in rules if r["oversized"]],
            "prune_candidates": [r["file"] for r in rules if r["recommendation"] == "prune_candidate"],
            "review_needed": [r["file"] for r in rules if r["recommendation"] == "review"],
            "details": rules,
        }, ensure_ascii=False, indent=2))
        return

    if prune_dry:
        candidates = [r for r in rules if r["recommendation"] == "prune_candidate"]
        if candidates:
            print(f"=== PRUNE CANDIDATES ({len(candidates)} rules) ===")
            for r in candidates:
                sc = r["rubric"]
                print(f"  {r['file']}: score={r['rubric_score']}/4 lines={r['lines']}")
                print(f"    F={sc['failure_backed']} T={sc['tool_enforceable']} D={sc['decision_encoding']} T={sc['triggerable']}")
        else:
            print("No prune candidates found.")
        return

    # Human-readable report
    print(f"=== Rule Auditor — {len(rules)} rules in {RULES_DIR} ===")
    print(f"Audited: {datetime.now().isoformat()}\n")

    # Summary
    oversized = [r for r in rules if r["oversized"]]
    no_fm = [r for r in rules if not r["has_frontmatter"]]
    prune = [r for r in rules if r["recommendation"] == "prune_candidate"]
    review = [r for r in rules if r["recommendation"] == "review"]
    unspecified = [r for r in rules if r["mode"] == "unspecified"]

    if oversized:
        print(f"⚠ OVERSIZED (>200 lines): {len(oversized)} — {', '.join(r['file'] for r in oversized)}")
    if no_fm:
        print(f"⚠ NO FRONTMATTER: {len(no_fm)} — {', '.join(r['file'] for r in no_fm)}")
    if unspecified:
        print(f"⚠ NO MODE: {len(unspecified)} — {', '.join(r['file'] for r in unspecified)}")
    if prune:
        print(f"🔴 PRUNE: {len(prune)} — {', '.join(r['file'] for r in prune)}")
    if review:
        print(f"🟡 REVIEW: {len(review)} — {', '.join(r['file'] for r in review)}")

    healthy = len(rules) - len(prune) - len(review)
    print(f"\n🟢 HEALTHY: {healthy}/{len(rules)}")
    print(f"\nDetail table:")
    print(f"{'Rule':<25} {'Lines':>5} {'Score':>5} {'FM':>4} {'Mode':<10} {'Rec'}")
    print("-" * 70)
    for r in rules:
        fm_flag = "✓" if r["has_frontmatter"] else "✗"
        print(f"{r['file']:<25} {r['lines']:>5} {r['rubric_score']:>4}/4 {fm_flag:>4} {r['mode']:<10} {r['recommendation']}")

if __name__ == "__main__":
    main()
