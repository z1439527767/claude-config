#!/usr/bin/env python3
"""heuristic-extract — distill concise rules from experience data (ERL mode).
Takes error logs, session notes, or free-text reflections and extracts
actionable, testable rules in the format: "When X, do Y" or "Never X".

Usage:
  python heuristic-extract.py < experience.txt
  python heuristic-extract.py "每次用 grep 不加 --line-buffered 就会卡住"
  python heuristic-extract.py --file session-notes.md
"""

import sys, re, json, io
from pathlib import Path
from collections import Counter

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def extract_heuristics(text: str) -> list[dict]:
    """Extract actionable heuristics from free text."""
    results = []
    seen = set()

    # Split into sentences
    sentences = re.split(r'[。！？；\n\.!\?;]+', text)

    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 6 or len(sent) > 300:
            continue

        rule = None
        rule_type = "insight"

        # Pattern 1: "每次/每当 X, Y" → When X, Y
        m = re.search(r'(?:每次|每当|一旦|every\s*time|whenever)\s*(.+?)(?:[,，]\s*|就|会|都|就?会)(.+)', sent, re.IGNORECASE)
        if m:
            rule = f"When {m.group(1).strip()}, {m.group(2).strip()}"
            rule_type = "procedure"

        # Pattern 2: "不要/别/不准 X" → Never X
        if not rule:
            m = re.search(r'(?:不要|别|不准|禁止|绝不|never|don\'?t|do\s*not|must\s*not)\s*(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"Never {m.group(1).strip()}"
                rule_type = "prevention"

        # Pattern 3: "必须/一定/总是 X" → Always X
        if not rule:
            m = re.search(r'(?:必须|一定要|总?是|永远要|always|must|should\s*always)\s*(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"Always {m.group(1).strip()}"
                rule_type = "procedure"

        # Pattern 4: "因为/由于 X, Y" → Root cause
        if not rule:
            m = re.search(r'(?:因为|由于|because|since|原因.*是)\s*(.+?)(?:[,，]\s*|所以|导致|造成|结果)(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"Cause: {m.group(1).strip()} → Effect: {m.group(2).strip()}"
                rule_type = "insight"

        # Pattern 5: "学到了/教训 X" → Lesson
        if not rule:
            m = re.search(r'(?:学到了|教训|lesson|learned|realized|发现)\s*[:：]?\s*(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"Lesson: {m.group(1).strip()}"
                rule_type = "insight"

        # Pattern 6: "如果/当 X, Y" → If X, then Y
        if not rule:
            m = re.search(r'(?:如果|当|if|when)\s*(.+?)(?:[,，]\s*|那么|就|应该|then)\s*(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"If {m.group(1).strip()}, then {m.group(2).strip()}"
                rule_type = "solution"

        # Pattern 7: "解决/修复 X" → Solution
        if not rule:
            m = re.search(r'(?:解决|修复|fix|solve|resolve)\s*(?:方案|方法|办法)?[:：]?\s*(.+)', sent, re.IGNORECASE)
            if m:
                rule = f"Solution: {m.group(1).strip()}"
                rule_type = "solution"

        if rule:
            rule = re.sub(r'[。，,\.\s]+$', '', rule)
            key = rule.lower()[:50]
            if key not in seen and 8 < len(rule) < 250:
                seen.add(key)
                results.append({
                    "rule": rule,
                    "source": sent[:150],
                    "type": rule_type,
                })

    return results


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif sys.argv[1] == "--file" and len(sys.argv) > 2:
            text = Path(sys.argv[2]).read_text(encoding="utf-8")
        else:
            text = " ".join(sys.argv[1:])
    else:
        if sys.stdin.isatty():
            print(__doc__)
            sys.exit(0)
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"rules": [], "total": 0}, ensure_ascii=False, indent=2))
        sys.exit(0)

    rules = extract_heuristics(text)

    # Count by type
    type_counts = Counter(r["type"] for r in rules)

    output = {
        "total": len(rules),
        "by_type": dict(type_counts),
        "rules": rules,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
