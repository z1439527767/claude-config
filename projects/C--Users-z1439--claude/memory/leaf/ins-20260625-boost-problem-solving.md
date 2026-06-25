---
name: ins-20260625-boost-problem-solving
description: Problem-solving capability boost session — 4 scripts rebuilt + evolution gate loosened + SOP created
metadata: 
  node_type: memory
  type: project
  confidence: 0.95
  date: 2026-06-25
  originSessionId: ca5376d8-bf74-4ff8-936f-f59ca68b2d66
---

## What was done
- Rebuilt 4 deleted scripts: sense-signals.py, guess-lang.py, scan-project.py, heuristic-extract.py
- Cleaned 22 orphan .pyc files without matching .py source
- Loosened evolution gate: 2min→30s interval, 10→20 per 7 days
- Switched strategy balanced→innovate
- Created problem-solving.md SOP (OODA loop + escalation chain)
- Fixed .gitignore self-ignoring bug + whitelisted rules/skills/agents/workflows/evolution

## Key findings
- **sense-signals.py was deleted** → friction detection was blind for unknown period
- **Evolution gate too tight** (10/7days) → only 1 evolution cycle in 24h
- **.gitignore was self-ignoring** → NEW files in .claude/rules/ silently ignored
- **Windows cp1252 encoding** → all Python scripts printing CJK need UTF-8 wrapper

## How to apply
- On each SessionStart, check `python scripts/health-check.py` for evolution cycle count
- Low evolution (<3/day) → check evolve-gate and strategy
- New scripts under .claude/rules/ must be force-added if not showing in git status
- All new Python tools must include `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` on Windows
