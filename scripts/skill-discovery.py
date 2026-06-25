#!/usr/bin/env python3
"""skill-discovery — analyze session patterns to detect repeatable workflows.
"Same task completed 3+ times → should be a SKILL.md"
Usage:
  python3 skill-discovery.py [--days 30] [--json] [--threshold 3]

Scans: session logs, tool usage patterns, task repetition.
Output: suggested skills with confidence scores.
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))

# Task pattern definitions — what we look for
TASK_PATTERNS = {
    "code_review": {
        "keywords": ["review", "审查", "PR", "pull request", "diff", "code review"],
        "tools": ["Read", "Grep", "Grep", "Edit"],
        "skill_name": "pr-review",
        "description": "Review PRs against a checklist",
    },
    "debug_loop": {
        "keywords": ["debug", "error", "bug", "fix", "调试", "修复", "报错"],
        "tools": ["Read", "Grep", "Bash", "Bash"],
        "skill_name": "debug-flow",
        "description": "Standard debugging workflow: reproduce → isolate → fix → verify",
    },
    "dependency_update": {
        "keywords": ["update", "upgrade", "install", "pip", "npm", "依赖", "更新"],
        "tools": ["Bash", "Bash", "Read"],
        "skill_name": "dep-update",
        "description": "Update dependencies safely: check changelog → update → test",
    },
    "refactor": {
        "keywords": ["refactor", "重构", "clean", "extract", "rename"],
        "tools": ["Grep", "Read", "Edit", "Edit"],
        "skill_name": "refactor-flow",
        "description": "Refactor safely: grep all refs → test → rename → verify",
    },
    "research": {
        "keywords": ["research", "search", "find", "look up", "研究", "搜索", "查"],
        "tools": ["WebSearch", "WebFetch", "Grep"],
        "skill_name": "deep-research",
        "description": "Research topic: search → fetch → verify → synthesize",
    },
    "config_change": {
        "keywords": ["config", "setting", "settings.json", "CLAUDE.md", "hook"],
        "tools": ["Read", "Edit", "Write"],
        "skill_name": "config-update",
        "description": "Update agent configuration: read → edit → verify syntax → restart",
    },
    "test_writing": {
        "keywords": ["test", "测试", "spec", "assert", "pytest", "vitest"],
        "tools": ["Write", "Bash", "Bash"],
        "skill_name": "write-tests",
        "description": "Write tests: happy path → error case → edge case → run",
    },
    "git_workflow": {
        "keywords": ["commit", "push", "snapshot", "branch", "merge"],
        "tools": ["Bash", "Bash"],
        "skill_name": "git-snapshot",
        "description": "Git workflow: status → add → commit → verify clean",
    },
}

def scan_evolution_log(days=30):
    """Scan evolution log for task patterns."""
    log_file = HOME / '.claude' / '.claude' / 'evolution_log.jsonl'
    if not log_file.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    events = []
    for line in log_file.read_text(encoding='utf-8', errors='ignore').split('\n'):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            ts = datetime.fromisoformat(e.get('timestamp', '2000-01-01T00:00:00'))
            if ts > cutoff:
                events.append(e)
        except Exception:
            pass
    return events

def scan_hook_perf():
    """Scan hook performance logs for tool usage patterns."""
    perf_dir = HOME / '.claude' / '.claude' / 'hook_perf'
    if not perf_dir.exists():
        return []
    tool_counts = Counter()
    for f in perf_dir.glob('*.jsonl'):
        for line in f.read_text(encoding='utf-8', errors='ignore').split('\n')[-100:]:
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                tool_counts[e.get('h', '')] += 1
            except Exception:
                pass
    return tool_counts

def discover_skills(days=30, threshold=3):
    """Main discovery logic."""
    events = scan_evolution_log(days)
    suggestions = []

    # Method 1: Keyword-based pattern matching in evolution events
    pattern_hits = defaultdict(int)
    pattern_contexts = defaultdict(list)
    for e in events:
        changes = e.get('changes', [])
        if isinstance(changes, list):
            changes_text = ' '.join(str(c) for c in changes)
        else:
            changes_text = str(changes)
        for pattern_name, pattern in TASK_PATTERNS.items():
            for kw in pattern["keywords"]:
                if kw.lower() in changes_text.lower():
                    pattern_hits[pattern_name] += 1
                    pattern_contexts[pattern_name].append(e.get('timestamp', ''))
                    break

    for pattern_name, count in pattern_hits.items():
        if count >= threshold:
            p = TASK_PATTERNS[pattern_name]
            suggestions.append({
                "skill_name": p["skill_name"],
                "pattern": pattern_name,
                "description": p["description"],
                "occurrences": count,
                "confidence": min(0.95, 0.5 + count * 0.1),
                "last_seen": max(pattern_contexts[pattern_name]) if pattern_contexts[pattern_name] else "unknown",
                "suggested_tools": p["tools"],
            })

    # Method 2: Check existing skills directory for gaps
    skills_dir = HOME / '.claude' / 'skills'
    existing_skills = set()
    if skills_dir.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
                existing_skills.add(skill_dir.name)

    for s in suggestions:
        s["already_exists"] = s["skill_name"] in existing_skills

    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    return suggestions

def main():
    use_json = "--json" in sys.argv
    days = 30
    threshold = 3
    for i, arg in enumerate(sys.argv):
        if arg == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])
        if arg == "--threshold" and i + 1 < len(sys.argv):
            threshold = int(sys.argv[i + 1])

    suggestions = discover_skills(days, threshold)

    if use_json:
        print(json.dumps({
            "window_days": days,
            "threshold": threshold,
            "suggestions": suggestions,
            "total": len(suggestions),
            "new": len([s for s in suggestions if not s["already_exists"]]),
        }, ensure_ascii=False, indent=2))
    else:
        new_skills = [s for s in suggestions if not s["already_exists"]]
        existing = [s for s in suggestions if s["already_exists"]]

        if new_skills:
            print(f"SKILL-DISCOVERY: {len(new_skills)} new skill suggestions ({days}d window, threshold={threshold})")
            for s in new_skills:
                print(f"  [{s['confidence']:.0%}] {s['skill_name']}: {s['description']}")
                print(f"         {s['occurrences']} occurrences, last: {s['last_seen'][:10]}")
                print(f"         scaffold: python3 scripts/skill-scaffold.py {s['skill_name']} \"{s['description']}\"")
        else:
            print(f"SKILL-DISCOVERY: no new skill suggestions ({days}d window, threshold={threshold})")

        if existing:
            print(f"  ({len(existing)} patterns already have skills)")

if __name__ == "__main__":
    main()
