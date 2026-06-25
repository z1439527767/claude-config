#!/usr/bin/env python3
"""session-summarizer — structured post-session summary for context handoff.
Generates: diff summary, key decisions, files changed, next steps.
Usage:
  python3 session-summarizer.py [--since "2026-06-25"] [--json] [--output summary.md]

Feeds into: next session's CLAUDE.md context, memory consolidation, knowledge graph.
"""
import sys, json, os, io, subprocess
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))

def get_git_log(since="yesterday"):
    """Get git log since a date."""
    cmd = ["git", "log", f"--since={since}", "--oneline", "--no-decorate"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=HOME)
        return result.stdout.strip().split('\n') if result.returncode == 0 else []
    except Exception:
        return []

def get_git_diff_stats(since="yesterday"):
    """Get git diff stats since a date."""
    cmd = ["git", "diff", "--stat", f"HEAD@{{{since}}}"] if "{" not in since else \
          ["git", "diff", "--stat", f"--since={since}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=HOME)
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""

def get_changed_files(since="yesterday"):
    """Get list of changed files."""
    cmd = ["git", "diff", "--name-only", f"--since={since}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=HOME)
        return result.stdout.strip().split('\n') if result.returncode == 0 else []
    except Exception:
        return []

def categorize_changes(files):
    """Categorize changed files."""
    categories = {
        "rules": [], "scripts": [], "hooks": [], "config": [],
        "docs": [], "lib": [], "other": [],
    }
    for f in files:
        if not f.strip():
            continue
        if 'rules/' in f:
            categories["rules"].append(f)
        elif 'scripts/hooks/' in f:
            categories["hooks"].append(f)
        elif 'scripts/lib/' in f:
            categories["lib"].append(f)
        elif 'scripts/' in f:
            categories["scripts"].append(f)
        elif f in ('settings.json', 'CLAUDE.md', 'AGENTS.md', 'CONVENTIONS.md'):
            categories["config"].append(f)
        elif f.endswith('.md'):
            categories["docs"].append(f)
        else:
            categories["other"].append(f)
    return categories

def detect_key_decisions(commits):
    """Heuristic-based detection of key decisions from commit messages."""
    decisions = []
    decision_keywords = ['feat:', 'fix:', 'refactor:', 'research:', 'add', 'remove',
                         'update', 'migrate', 'fuse', 'integrate']
    for commit in commits:
        for kw in decision_keywords:
            if kw in commit.lower():
                decisions.append(commit)
                break
    return decisions[:10]  # Top 10

def generate_summary(since="yesterday", output_file=None):
    """Generate full session summary."""
    commits = get_git_log(since)
    files = get_changed_files(since)
    categories = categorize_changes(files)
    decisions = detect_key_decisions(commits)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "since": since,
        "commits": len(commits),
        "files_changed": len(files),
        "categories": {k: len(v) for k, v in categories.items() if v},
        "key_decisions": decisions,
        "file_breakdown": categories,
    }

    if output_file:
        md = f"""# Session Summary — {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Stats
- **Commits**: {len(commits)}
- **Files Changed**: {len(files)}
- **Period**: {since}

## Changes by Category
"""
        for cat, cat_files in sorted(categories.items()):
            if cat_files:
                md += f"\n### {cat.title()} ({len(cat_files)})\n"
                for f in cat_files[:10]:
                    md += f"- {f}\n"
                if len(cat_files) > 10:
                    md += f"- ... and {len(cat_files) - 10} more\n"

        if decisions:
            md += "\n## Key Decisions\n"
            for d in decisions:
                md += f"- {d}\n"

        md += f"\n## Handoff\n"
        md += f"- Review changed files above for context\n"
        md += f"- Run `python3 scripts/health-check.py` for system status\n"
        md += f"- Run `python3 scripts/rule-auditor.py` if rules were modified\n"

        Path(output_file).write_text(md, encoding='utf-8')
        print(f"SESSION-SUMMARY: written to {output_file}")

    return summary

def main():
    use_json = "--json" in sys.argv
    since = "yesterday"
    output_file = None

    for i, arg in enumerate(sys.argv):
        if arg == "--since" and i + 1 < len(sys.argv):
            since = sys.argv[i + 1]
        if arg == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]

    summary = generate_summary(since, output_file)

    if use_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif not output_file:
        print(f"SESSION-SUMMARY: {summary['commits']} commits, {summary['files_changed']} files changed ({since})")
        for cat, count in sorted(summary["categories"].items()):
            print(f"  {cat}: {count} files")
        if summary["key_decisions"]:
            print(f"  Key decisions: {len(summary['key_decisions'])}")
            for d in summary["key_decisions"][:3]:
                print(f"    - {d}")

if __name__ == "__main__":
    main()
