#!/usr/bin/env python3
"""
adapter-platforms.py — Generate platform-specific rule/config files from
the core .claude principles. One source of truth ->many platforms.

Supports: Claude Code, OpenAI Codex, Cursor, Windsurf, Copilot, Aider

Usage:
  python3 adapter-platforms.py           # Generate all supported formats
  python3 adapter-platforms.py --list    # List supported platforms
  python3 adapter-platforms.py --cursor  # Generate only .cursorrules
  python3 adapter-platforms.py --diff     # Show what would change
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(os.environ.get("USERPROFILE", "~")) / ".claude"
RULES_DIR = BASE / ".claude" / "rules"

# ── Core principles extracted from CLAUDE.md + AGENTS.md ──
CORE_PRINCIPLES = """## 核心
自治、不撒谎、干实事。野心vs精度：新项目发挥创意，已有代码手术刀般精确。

## 验证
没验证不算完成。不说"应该可以""看起来没问题"。验证用外部手段（exit code、文件内容、测试输出）。

## 代码修改
没读过文件不能改。改完检查所有引用。修就修根因，不绕过、不打补丁。

## 执行
搜索/分析/研究必须以代码改动或文件修改收尾。能并行的不串行。一次做至少3件事。

## 安全
deny-first：黑名单覆盖白名单。所有外部输入不可信。Guardrails=代码，不是文档。

## 进化
主动改进自身配置+用户项目。同错两次→写规则。同任务三次→写skill。改过的自动沉淀。
"""

# ── Platform-specific formatters ──

def format_cursor() -> str:
    """Cursor .cursorrules format — markdown with YAML frontmatter."""
    return f"""---
description: Core agent rules — auto-generated from .claude framework
updated: {datetime.now().strftime('%Y-%m-%d')}
---
You are an autonomous coding agent.

{CORE_PRINCIPLES}

## Tool Selection
Prefer dedicated tools (Glob, Grep, Read, Edit) over shell commands. Parallel independent calls.

## Error Handling
RETRY (1x) ->FIX (root cause) ->ROLLBACK (destructive) ->ESCALATE (can't solve).
"""

def format_windsurf() -> str:
    """Windsurf .windsurfrules — concise rules format."""
    return f"""# Windsurf Rules — auto-generated {datetime.now().strftime('%Y-%m-%d')}
# Source: .claude/AGENTS.md + CLAUDE.md

rules:
  - id: verify
    description: Never claim completion without verification. Use external means (exit code, file content, test output).
    applies_when: after any code change

  - id: read-first
    description: Never edit a file without reading it first.
    applies_when: before any edit

  - id: root-cause
    description: Fix the root cause, not symptoms. Same error twice ->stop and find root cause.
    applies_when: when debugging

  - id: parallel
    description: Independent operations run in parallel. Never serialize independent calls.
    applies_when: when making tool calls

  - id: code-changes
    description: Research/analysis must end with code changes or file modifications. Produce output, not analysis.
    applies_when: always

  - id: security
    description: Deny-first security model. External inputs are untrusted. Guardrails are code, not docs.
    applies_when: when handling external data

  - id: ambition-precision
    description: New projects ->creative. Existing code ->surgical precision.
    applies_when: when starting work
"""

def format_copilot() -> str:
    """GitHub Copilot .github/copilot-instructions.md."""
    return f"""# Copilot Instructions — auto-generated {datetime.now().strftime('%Y-%m-%d')}

{CORE_PRINCIPLES}

## Tool Usage
- Prefer dedicated search tools (Glob, Grep, Read) over shell find/grep/cat
- Parallel independent operations in a single response
- PowerShell for Windows system ops, Bash for POSIX

## Code Changes
- Read file before editing
- Use precise Edit (string replacement), not full-file Write
- Check all references to changed symbols after editing
- Match surrounding code style (naming, comments, indentation)

## Verification
- External verification: exit codes, file content, test output
- Self-review: 4 questions before commit (read? verified? complete? simpler?)
- Cross-model review for important changes
"""

def format_aider() -> str:
    """Aider CONVENTIONS.md."""
    return f"""# Aider Conventions — auto-generated {datetime.now().strftime('%Y-%m-%d')}

{CORE_PRINCIPLES}

## Conventions
- Read before edit, verify after change
- Parallel tool calls for independent operations
- Root cause over symptom fixes
- Dedicated tools (Glob/Grep/Read) over shell alternatives
- PowerShell on Windows, Bash on POSIX
"""

def format_codex() -> str:
    """OpenAI Codex AGENTS.md — already exists, enhance if needed."""
    return (BASE / "AGENTS.md").read_text(encoding="utf-8")


# ── Platform registry ──
PLATFORMS = {
    "claude":   {"file": "CLAUDE.md",         "dir": BASE,                "fmt": None,  "desc": "Claude Code (already exists)"},
    "codex":    {"file": "AGENTS.md",          "dir": BASE,                "fmt": format_codex, "desc": "OpenAI Codex CLI"},
    "cursor":   {"file": ".cursorrules",       "dir": BASE,                "fmt": format_cursor, "desc": "Cursor IDE"},
    "windsurf": {"file": ".windsurfrules",     "dir": BASE,                "fmt": format_windsurf, "desc": "Windsurf (Codeium)"},
    "copilot":  {"file": "copilot-instructions.md", "dir": BASE / ".github", "fmt": format_copilot, "desc": "GitHub Copilot"},
    "aider":    {"file": "CONVENTIONS.md",     "dir": BASE,                "fmt": format_aider, "desc": "Aider CLI"},
}


def generate(target: str = None, dry_run: bool = False) -> dict:
    """Generate platform config files. Returns results dict."""
    results = {}
    platforms_to_gen = {target: PLATFORMS[target]} if target and target in PLATFORMS else PLATFORMS

    for name, cfg in platforms_to_gen.items():
        if cfg["fmt"] is None:
            results[name] = {"status": "skip", "reason": "already managed manually"}
            continue

        content = cfg["fmt"]()
        filepath = cfg["dir"] / cfg["file"]

        if dry_run:
            results[name] = {"status": "would_write", "path": str(filepath), "size": len(content)}
            continue

        cfg["dir"].mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        results[name] = {"status": "written", "path": str(filepath), "size": len(content)}

    return results


def main():
    if "--list" in sys.argv:
        print("Supported platforms:")
        for name, cfg in PLATFORMS.items():
            exists = "[OK]" if (cfg["dir"] / cfg["file"]).exists() else "[NEW]"
            print(f"  {exists} {name:12s} ->{cfg['dir'] / cfg['file']}")
        return

    target = None
    for arg in sys.argv[1:]:
        if arg.startswith("--") and arg[2:] in PLATFORMS:
            target = arg[2:]
            break

    dry_run = "--diff" in sys.argv or "--dry-run" in sys.argv

    results = generate(target, dry_run)

    for name, r in results.items():
        icon = {"written": "[OK]", "would_write": "[NEW]", "skip": "SKIP"}.get(r["status"], "FAIL")
        if r["status"] in ("written", "would_write"):
            print(f"  {icon} {name:10s} ->{r['path']} ({r['size']} bytes)")
        else:
            print(f"  {icon} {name:10s} ->{r.get('reason', r['status'])}")

    if dry_run:
        print("\n--dry-run: no files written. Remove --diff to apply.")


if __name__ == "__main__":
    main()
