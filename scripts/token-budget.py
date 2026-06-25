#!/usr/bin/env python3
"""token-budget — context budget estimation and monitoring.
Reads session metadata from stdin or file, estimates token usage.
Usage: python3 token-budget.py                  # check current
        python3 token-budget.py --warn 0.7      # warn if >70% used"""

import sys, os, json
from pathlib import Path
from datetime import datetime, timedelta

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'

# Claude Code session keeps history in history.jsonl
# Each line = one turn. Rough estimate: 500-2000 tokens per line.
EST_TOKENS_PER_LINE = 800
MAX_CONTEXT = 200000  # Claude max context

def estimate_context_usage():
    """Estimate context usage from session history."""
    history_file = CLAUDE / 'history.jsonl'
    if not history_file.exists():
        return {'error': 'no history file'}

    lines = history_file.read_text(encoding='utf-8', errors='ignore').strip().split('\n')
    total_lines = len([l for l in lines if l.strip()])

    # Estimate: recent 200 lines are in context
    recent = min(total_lines, 200)
    est_tokens = recent * EST_TOKENS_PER_LINE
    usage_pct = round(est_tokens / MAX_CONTEXT, 3)

    # Check .session-state.json for more accurate data
    state_file = CLAUDE / '.session-state.json'
    last_session = 'unknown'
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            last_session = state.get('lastSessionEnd', 'unknown')
        except Exception:
            pass

    return {
        'total_lines': total_lines,
        'recent_lines': recent,
        'est_tokens': est_tokens,
        'max_tokens': MAX_CONTEXT,
        'usage_pct': usage_pct,
        'last_session': last_session,
        'status': 'ok' if usage_pct < 0.4 else ('warn' if usage_pct < 0.7 else 'critical')
    }

def check_file_sizes():
    """Check key file sizes that contribute to context."""
    files = {
        'history.jsonl': CLAUDE / 'history.jsonl',
        'events.jsonl': CLAUDE / 'events.jsonl',
        'metacog-learnings.jsonl': CLAUDE / 'metacog-learnings.jsonl',
    }
    sizes = {}
    for name, path in files.items():
        if path.exists():
            size_kb = path.stat().st_size / 1024
            sizes[name] = round(size_kb, 1)
    return sizes

def main():
    result = estimate_context_usage()
    sizes = check_file_sizes()

    warn_threshold = 0.7
    if '--warn' in sys.argv:
        idx = sys.argv.index('--warn')
        warn_threshold = float(sys.argv[idx + 1])

    if '--json' in sys.argv:
        print(json.dumps({**result, 'file_sizes_kb': sizes}, ensure_ascii=False, indent=2))
    else:
        status_icon = 'OK' if result['status'] == 'ok' else ('WARN' if result['status'] == 'warn' else 'CRIT')
        print(f"Context: {status_icon} ({result['usage_pct']*100:.1f}% est.)")
        print(f"  Est tokens: {result['est_tokens']:,} / {result['max_tokens']:,}")
        print(f"  History: {result['total_lines']} lines ({result['recent_lines']} recent)")
        print(f"  Files: history={sizes.get('history.jsonl','?')}KB events={sizes.get('events.jsonl','?')}KB")
        if result['usage_pct'] > warn_threshold:
            print(f"  WARNING: Context usage >{warn_threshold*100:.0f}%. Consider /compact or starting new session.")
        if result['status'] == 'critical':
            print(f"  ACTION: /compact immediately. Context degradation expected.")

    # Exit code for scripting
    if result['status'] == 'critical':
        sys.exit(2)
    elif result['status'] == 'warn':
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
