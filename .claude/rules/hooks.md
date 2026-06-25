---
paths:
  - "hooks.json"
  - "settings.json"
---

# Hooks & Settings Rules
> 🥇 Operational | Load: on hook execution | Scope: all hook scripts | Overrides: N/A (deterministic enforcement)

- Hooks run OUTSIDE context (zero token cost). Use for deterministic enforcement, not advisory guidance.
- Exit 0 = allow. Exit 2 = block (stderr → Claude). Other non-zero = warn but proceed.
- PreToolUse hooks: keep under 10s timeout. Blocking faster than asking.
- Stop hooks: always check `stop_hook_active` env var to prevent infinite re-triggers.
- SessionStart: handoff + tasks only. No dashboards. Token budget: ~200 tokens max.
- Use `"runInBackground": true` for non-blocking PostToolUse operations (formatting, linting).
