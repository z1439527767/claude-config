#!/usr/bin/env python3
"""context-monitor — active context budget tracking with threshold alerts.
Based on Sourcegraph Context Engineering guide: <60% safe, >80% warn, >85% critical.
Usage:
  python3 context-monitor.py [--json] [--alert-threshold 80]

Monitors: token usage, tool call counts, file read counts, session duration.
Alerts: when approaching context window limits.
"""
import sys, json, os, io
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
STATE_FILE = HOME / '.claude' / '.claude' / 'context_monitor.json'
MAX_WINDOW = 200000  # Default Claude max context
SAFE_LINE = 0.60     # 60% = safe
WARN_LINE = 0.80     # 80% = warning
CRITICAL_LINE = 0.85 # 85% = hallucinations spike

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "sessions": [],
        "alerts": [],
        "total_tool_calls": 0,
        "total_files_read": 0,
        "compactions": 0,
    }

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def estimate_tokens(text):
    """Rough token estimation: ~4 chars per token for English, ~2 for code."""
    if not text:
        return 0
    # Conservative estimate: 3 chars per token
    return len(text) // 3

def check_thresholds(estimated_tokens, state):
    """Check against thresholds and generate alerts."""
    pct = estimated_tokens / MAX_WINDOW * 100

    if pct >= CRITICAL_LINE * 100:
        level = "CRITICAL"
        msg = f"Context at {pct:.0f}% — hallucinations spike above 85%. Compact NOW."
    elif pct >= WARN_LINE * 100:
        level = "WARNING"
        msg = f"Context at {pct:.0f}% — approaching danger zone. Prune low-signal content."
    elif pct >= SAFE_LINE * 100:
        level = "INFO"
        msg = f"Context at {pct:.0f}% — within operating range."
    else:
        level = "OK"
        msg = f"Context at {pct:.0f}% — healthy."

    alert = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "estimated_tokens": estimated_tokens,
        "pct": round(pct, 1),
        "message": msg,
    }

    if level in ("CRITICAL", "WARNING"):
        state["alerts"].append(alert)
        # Keep last 50 alerts
        state["alerts"] = state["alerts"][-50:]

    return alert

def analyze_recent_activity(state):
    """Analyze recent session activity patterns."""
    recent = state.get("sessions", [])[-5:]
    if not recent:
        return {}

    avg_tool_calls = sum(s.get("tool_calls", 0) for s in recent) / len(recent)
    avg_files_read = sum(s.get("files_read", 0) for s in recent) / len(recent)
    total_compactions = state.get("compactions", 0)

    issues = []
    if avg_tool_calls > 50:
        issues.append(f"High avg tool calls ({avg_tool_calls:.0f}/session) — consider using Workflow for parallelization")
    if avg_files_read > 30:
        issues.append(f"High avg files read ({avg_files_read:.0f}/session) — narrow scope or use subagents")
    if total_compactions > 10:
        issues.append(f"Frequent compactions ({total_compactions}) — sessions may be too long, fork earlier")

    return {
        "avg_tool_calls": round(avg_tool_calls, 1),
        "avg_files_read": round(avg_files_read, 1),
        "compactions": total_compactions,
        "issues": issues,
    }

def main():
    use_json = "--json" in sys.argv
    state = load_state()

    # Estimate current context usage (rough: based on files read count * avg file size)
    # This is a heuristic — actual token counting requires API access
    estimated = state.get("total_files_read", 0) * 2000  # ~2K tokens per file avg
    estimated += state.get("total_tool_calls", 0) * 200   # ~200 tokens per tool call
    estimated = min(estimated, MAX_WINDOW)  # Cap at max

    alert = check_thresholds(estimated, state)
    activity = analyze_recent_activity(state)

    result = {
        "timestamp": datetime.now().isoformat(),
        "alert": alert,
        "activity": activity,
        "thresholds": {
            "safe_pct": int(SAFE_LINE * 100),
            "warn_pct": int(WARN_LINE * 100),
            "critical_pct": int(CRITICAL_LINE * 100),
            "max_window": MAX_WINDOW,
        },
        "recommendations": [
            "Keep one thread per task — don't use one thread for entire project",
            "Fork session when context exceeds 60% for unrelated work",
            "Use subagents for bounded exploration (clean context per agent)",
            "Compact old turns into summaries before they crowd out instructions",
            "Re-rank: retrieve 50 candidates, keep only top-5 in context",
        ],
    }

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"CONTEXT-MONITOR: [{alert['level']}] {alert['message']}")
        if activity.get("issues"):
            for issue in activity["issues"]:
                print(f"  ⚠ {issue}")
        print(f"  Sessions tracked: {len(state.get('sessions', []))}")
        print(f"  Total compactions: {state.get('compactions', 0)}")
        print(f"  Recent alerts: {len([a for a in state.get('alerts', []) if a['level'] in ('CRITICAL', 'WARNING')])}")

if __name__ == "__main__":
    main()
