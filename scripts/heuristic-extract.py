#!/usr/bin/env python3
"""heuristic-extract — distill concise heuristics from agent experience logs.
ERL pattern: heuristics outperform trajectory prompts for cross-task transfer (+7.8% Gaia2).
Reads evolution log + failure log, extracts reusable heuristics.
Usage: python3 heuristic-extract.py [--since 7d]"""

import sys, json, os
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'

def load_evolution_log(since_days=7):
    """Load recent evolution events."""
    log_file = CLAUDE / '.claude' / 'evolution_log.jsonl'
    if not log_file.exists():
        return []
    cutoff = datetime.now() - timedelta(days=since_days)
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

def load_failures(since_days=7):
    """Load recent tool failures."""
    fail_dir = CLAUDE / '.claude' / 'tool_failures'
    if not fail_dir.exists():
        return []
    cutoff = datetime.now() - timedelta(days=since_days)
    failures = []
    for f in fail_dir.glob('*.jsonl'):
        for line in f.read_text(encoding='utf-8', errors='ignore').split('\n'):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e.get('timestamp', '2000-01-01T00:00:00'))
                if ts > cutoff:
                    failures.append(e)
            except Exception:
                pass
    return failures

def extract_heuristics(events, failures):
    """Extract concise, reusable heuristics from events and failures."""
    heuristics = []

    # Pattern 1: Recurring failure tools
    tool_fails = Counter(f.get('tool_name', 'unknown') for f in failures)
    for tool, count in tool_fails.most_common(3):
        if count >= 3:
            heuristics.append({
                'pattern': 'recurring_tool_failure',
                'heuristic': f'Before calling {tool}, verify inputs and check if a simpler alternative exists.',
                'evidence': f'{tool} failed {count}x in recent window',
                'confidence': min(0.9, 0.5 + count * 0.1),
            })

    # Pattern 2: Evolution activity suggests over-evolution
    l1_count = sum(1 for e in events for c in e.get('changes', []) if 'L1:' in str(c))
    if l1_count >= 5:
        heuristics.append({
            'pattern': 'rapid_rule_growth',
            'heuristic': 'Too many new rules added recently. Instead of adding rules, remove conflicting or outdated ones first.',
            'evidence': f'{l1_count} L1 rule changes in window',
            'confidence': 0.7,
        })

    # Pattern 3: No evolution = stagnation
    if len(events) == 0:
        heuristics.append({
            'pattern': 'stagnation',
            'heuristic': 'No evolution activity detected. Run self-audit to identify accumulated friction.',
            'evidence': '0 evolution events in window',
            'confidence': 0.6,
        })

    # Pattern 4: Common failure patterns
    error_msgs = [f.get('error', '')[:100] for f in failures if f.get('error')]
    if error_msgs:
        encoding_errors = sum(1 for e in error_msgs if 'encode' in e.lower() or 'decode' in e.lower() or 'charmap' in e.lower())
        permission_errors = sum(1 for e in error_msgs if 'permission' in e.lower() or 'denied' in e.lower() or 'EACCES' in e)
        not_found_errors = sum(1 for e in error_msgs if 'not found' in e.lower() or 'ENOENT' in e.lower())

        if not_found_errors >= 3:
            heuristics.append({
                'pattern': 'missing_files',
                'heuristic': 'Multiple file-not-found errors. Always Glob or Test-Path before Read. Verify paths with absolute references.',
                'evidence': f'{not_found_errors} not-found errors in window',
                'confidence': 0.85,
            })
        if encoding_errors >= 2:
            heuristics.append({
                'pattern': 'encoding_issues',
                'heuristic': 'Always set UTF-8 encoding explicitly: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8") for Python, [Console]::OutputEncoding for PS.',
                'evidence': f'{encoding_errors} encoding errors in window',
                'confidence': 0.85,
            })
        if permission_errors >= 2:
            heuristics.append({
                'pattern': 'permission_issues',
                'heuristic': 'Permission errors recurring. Check file ownership and ACLs before attempting operations. Use try/catch with fallback paths.',
                'evidence': f'{permission_errors} permission errors in window',
                'confidence': 0.8,
            })

    return heuristics

def main():
    since_days = 7
    for i, arg in enumerate(sys.argv):
        if arg == '--since' and i + 1 < len(sys.argv):
            d = sys.argv[i + 1]
            since_days = int(d.rstrip('d'))

    events = load_evolution_log(since_days)
    failures = load_failures(since_days)
    heuristics = extract_heuristics(events, failures)

    if '--json' in sys.argv:
        print(json.dumps({
            'window_days': since_days,
            'events': len(events),
            'failures': len(failures),
            'heuristics': heuristics,
        }, ensure_ascii=False, indent=2))
    elif heuristics:
        print(f"Extracted {len(heuristics)} heuristics from {len(events)} events + {len(failures)} failures ({since_days}d window):")
        for h in heuristics:
            print(f"  [{h['confidence']:.0%}] {h['heuristic']}")
            print(f"         Evidence: {h['evidence']}")
    else:
        print(f"No heuristics extracted ({len(events)} events, {len(failures)} failures in {since_days}d)")

if __name__ == '__main__':
    main()
