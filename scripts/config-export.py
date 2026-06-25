#!/usr/bin/env python3
"""config-export — export CLAUDE.md + rules/ to other agent formats.
Supports: Codex AGENTS.md, Cursor .mdc, Windsurf .windsurfrules, Gemini GEMINI.md, Aider CONVENTIONS.md.
Usage:
  python3 config-export.py --target codex    # Export to Codex AGENTS.md
  python3 config-export.py --target cursor   # Export to Cursor .cursor/rules/*.mdc
  python3 config-export.py --target windsurf # Export to Windsurf directory
  python3 config-export.py --target gemini   # Export to Gemini GEMINI.md
  python3 config-export.py --target aider    # Export Aider format
  python3 config-export.py --target all      # Export all formats
  python3 config-export.py --list            # List supported targets
"""
import sys, json, os, io
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
RULES_DIR = HOME / '.claude' / '.claude' / 'rules'
CLAUDE_MD = HOME / '.claude' / 'CLAUDE.md'
AGENTS_MD = HOME / '.claude' / 'AGENTS.md'
CONVENTIONS_MD = HOME / '.claude' / 'CONVENTIONS.md'

SUPPORTED = ['codex', 'cursor', 'windsurf', 'gemini', 'aider', 'all']

def read_rules():
    """Read all rule files."""
    rules = []
    if RULES_DIR.exists():
        for f in sorted(RULES_DIR.glob('*.md')):
            content = f.read_text(encoding='utf-8', errors='ignore')
            rules.append({"name": f.stem, "content": content, "file": str(f)})
    return rules

def export_codex(output_dir="."):
    """Export to Codex AGENTS.md format (single file)."""
    rules = read_rules()
    lines = [
        "# AGENTS.md — Auto-generated from Claude Code config",
        f"# Generated: {datetime.now().isoformat()}",
        "",
    ]
    if CLAUDE_MD.exists():
        lines.append(CLAUDE_MD.read_text(encoding='utf-8'))
    if AGENTS_MD.exists():
        lines.append("\n" + AGENTS_MD.read_text(encoding='utf-8'))
    if CONVENTIONS_MD.exists():
        lines.append("\n" + CONVENTIONS_MD.read_text(encoding='utf-8'))

    lines.append("\n## Rules\n")
    for r in rules:
        lines.append(f"\n### {r['name']}\n")
        lines.append(r['content'])

    out = Path(output_dir) / "AGENTS.md"
    out.write_text('\n'.join(lines), encoding='utf-8')
    return str(out)

def export_cursor(output_dir=".cursor/rules"):
    """Export to Cursor .cursor/rules/*.mdc format."""
    rules = read_rules()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files = []

    # AGENTS.md as always-applied rule
    agents_mdc = Path(output_dir) / "00-agents.mdc"
    content = "---\nalwaysApply: true\ndescription: Core agent rules and invariants\n---\n\n"
    if AGENTS_MD.exists():
        content += AGENTS_MD.read_text(encoding='utf-8')
    agents_mdc.write_text(content, encoding='utf-8')
    files.append(str(agents_mdc))

    for r in rules:
        mdc_file = Path(output_dir) / f"{r['name']}.mdc"
        # Detect mode from frontmatter
        mode = "alwaysApply: true"
        if 'mode: manual' in r['content']:
            mode = "alwaysApply: false"
        content = f"---\n{mode}\ndescription: Rule: {r['name']}\n---\n\n{r['content']}"
        mdc_file.write_text(content, encoding='utf-8')
        files.append(str(mdc_file))

    return f"{len(files)} files in {output_dir}/"

def export_windsurf(output_dir=".windsurf/rules"):
    """Export to Windsurf .windsurf/rules/ format."""
    rules = read_rules()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    files = []

    for r in rules:
        ws_file = Path(output_dir) / f"{r['name']}.md"
        trigger = "always_on"
        if 'mode: manual' in r['content']:
            trigger = "manual"
        elif 'mode: auto' in r['content']:
            trigger = "model_decision"
        content = f"---\ntrigger: {trigger}\ndescription: {r['name']}\n---\n\n{r['content']}"
        ws_file.write_text(content, encoding='utf-8')
        files.append(str(ws_file))

    return f"{len(files)} files in {output_dir}/"

def export_gemini(output_dir="."):
    """Export to Gemini GEMINI.md format (single file)."""
    rules = read_rules()
    lines = [
        "# GEMINI.md — Auto-generated from Claude Code config",
        f"# Generated: {datetime.now().isoformat()}",
        "",
        "## Core",
    ]
    if AGENTS_MD.exists():
        lines.append(AGENTS_MD.read_text(encoding='utf-8'))
    if CONVENTIONS_MD.exists():
        lines.append("\n" + CONVENTIONS_MD.read_text(encoding='utf-8'))

    lines.append("\n## Behavioral Rules\n")
    for r in rules:
        lines.append(f"\n### {r['name']}\n")
        lines.append(r['content'])

    out = Path(output_dir) / "GEMINI.md"
    out.write_text('\n'.join(lines), encoding='utf-8')
    return str(out)

def export_aider(output_dir="."):
    """Export Aider CONVENTIONS.md (already exists, just copy/symlink)."""
    if CONVENTIONS_MD.exists():
        out = Path(output_dir) / "CONVENTIONS.md"
        out.write_text(CONVENTIONS_MD.read_text(encoding='utf-8'))
        return str(out)
    return "CONVENTIONS.md not found — create it first"

EXPORTERS = {
    "codex": export_codex,
    "cursor": export_cursor,
    "windsurf": export_windsurf,
    "gemini": export_gemini,
    "aider": export_aider,
}

def main():
    if "--list" in sys.argv:
        print("Supported export targets:")
        for t in SUPPORTED:
            print(f"  {t}")
        return

    target = "all"
    for i, arg in enumerate(sys.argv):
        if arg == "--target" and i + 1 < len(sys.argv):
            target = sys.argv[i + 1]

    if target not in SUPPORTED:
        print(f"Unknown target: {target}. Use --list to see supported targets.")
        return

    targets = list(EXPORTERS.keys()) if target == "all" else [target]

    for t in targets:
        try:
            result = EXPORTERS[t]()
            print(f"  [{t}] → {result}")
        except Exception as e:
            print(f"  [{t}] ERROR: {e}")

if __name__ == "__main__":
    main()
