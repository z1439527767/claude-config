#!/usr/bin/env python3
"""skill-scaffold — Auto-generate SKILL.md following agentskills.io spec.
Usage:
  python3 skill-scaffold.py <name> <description> [--category <cat>] [--global]

Creates:
  .claude/skills/<name>/SKILL.md   (project) or
  ~/.claude/skills/<name>/SKILL.md (global with --global)

Frontmatter: name (kebab-case, 1-64 chars), description (1-1024 chars)
Format: agentskills.io v1.0 spec, compatible with 32+ tools.
"""
import sys, os, re
from pathlib import Path

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
SKILL_TEMPLATE = """---
name: {name}
description: {description}
---

# {title}

## When to Use
- {description}
- Trigger phrases: {triggers}

## Instructions

### Step 1: Understand the context
- Read relevant files and understand the current state
- Ask clarifying questions if the scope is ambiguous

### Step 2: Execute
- Follow project conventions (see CONVENTIONS.md and CLAUDE.md)
- Make changes incrementally, verify each step

### Step 3: Verify
- Run tests, linters, or manual checks to confirm the change works
- Review the diff for unintended side effects

## What NOT to Do
- Do not modify files outside the scope of this task
- Do not skip verification steps

## References
- CONVENTIONS.md — Project coding standards
- CLAUDE.md — Agent behavior rules
"""

def to_kebab(name):
    """Convert any string to valid kebab-case."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s-]', '', name)
    name = re.sub(r'[\s_]+', '-', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    if len(name) > 64:
        name = name[:64].rstrip('-')
    if not name:
        name = "unnamed-skill"
    return name

def to_title(name):
    """Convert kebab-case to Title Case."""
    return " ".join(w.capitalize() for w in name.split('-'))

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nExample:")
        print("  python3 skill-scaffold.py pr-review 'Review PRs against checklist' --category review")
        return

    raw_name = sys.argv[1]
    description = sys.argv[2]
    use_global = "--global" in sys.argv

    name = to_kebab(raw_name)
    title = to_title(name)

    # Validate
    if len(name) < 1 or len(name) > 64:
        print(f"ERROR: name must be 1-64 chars (got {len(name)}: '{name}')")
        return
    if len(description) < 1 or len(description) > 1024:
        print(f"ERROR: description must be 1-1024 chars (got {len(description)})")
        return
    if not re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', name):
        print(f"ERROR: name must match ^[a-z][a-z0-9-]*[a-z0-9]$ (got '{name}')")
        return

    base = HOME / '.claude' / 'skills' if use_global else Path.cwd() / '.claude' / 'skills'
    skill_dir = base / name

    if skill_dir.exists():
        print(f"ERROR: skill directory already exists: {skill_dir}")
        return

    # Generate trigger phrases from description
    triggers = f'"{description.lower()[:50]}", "help me {name.replace("-", " ")}"'

    content = SKILL_TEMPLATE.format(
        name=name,
        description=description,
        title=title,
        triggers=triggers,
    )

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding='utf-8')

    print(f"SKILL: created {skill_file}")
    print(f"       name: {name}")
    print(f"       description: {description}")
    print(f"       scope: {'global' if use_global else 'project'}")
    print(f"       Next: edit the Instructions section in SKILL.md to add real steps")

if __name__ == "__main__":
    main()
