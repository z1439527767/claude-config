#!/usr/bin/env python3
"""health-check — signal dashboard for the Ralph Loop framework.
Distilled from SIA dashboard + Evolver signal extraction.
Usage: python3 health-check.py [--json]"""

import sys, os, json
from pathlib import Path
from datetime import datetime, timedelta

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'

def check_disk():
    """Check available disk space."""
    try:
        import shutil
        usage = shutil.disk_usage(str(HOME))
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct = (usage.used / usage.total) * 100
        return {
            'free_gb': round(free_gb, 1),
            'total_gb': round(total_gb, 1),
            'used_pct': round(pct, 1),
            'status': 'ok' if free_gb > 10 else ('warn' if free_gb > 5 else 'critical')
        }
    except Exception:
        return {'status': 'unknown'}

def check_git():
    """Check git status."""
    import subprocess
    try:
        r = subprocess.run(['git', '-C', str(CLAUDE), 'status', '--porcelain'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5)
        dirty = len([l for l in r.stdout.split('\n') if l.strip()])
        r2 = subprocess.run(['git', '-C', str(CLAUDE), 'log', '--oneline', '-1'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5)
        return {
            'dirty_files': dirty,
            'last_commit': r2.stdout.strip()[:60],
            'status': 'ok' if dirty < 10 else 'warn'
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def check_hooks():
    """Check hook script health."""
    hooks_dir = CLAUDE / 'scripts' / 'hooks'
    if not hooks_dir.exists():
        return {'status': 'error', 'error': 'hooks directory missing'}

    total = 0
    heavy = []
    for f in hooks_dir.glob('*.ps1'):
        total += 1
        lines = len(f.read_text(encoding='utf-8', errors='ignore').split('\n'))
        if lines > 200:
            heavy.append({'name': f.name, 'lines': lines})

    return {
        'total': total,
        'heavy': heavy,
        'status': 'ok' if not heavy else 'warn'
    }

def check_evolution():
    """Check evolution history."""
    evo_dir = CLAUDE / '.claude' / 'evolution'
    if not evo_dir.exists():
        return {'status': 'ok', 'cycles': 0, 'message': 'no evolution yet'}

    cycles = len(list(evo_dir.glob('*.json')))
    # Check for recent evolution activity
    recent = 0
    cutoff = datetime.now() - timedelta(hours=24)
    for f in evo_dir.glob('*.json'):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime > cutoff:
            recent += 1

    return {
        'status': 'ok',
        'cycles': cycles,
        'recent_24h': recent,
    }

def check_memory():
    """Check memory health."""
    mem_dirs = list((CLAUDE / 'projects').glob('*/memory'))
    mem_dir = mem_dirs[0] if mem_dirs else CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'
    if not mem_dir.exists():
        return {'status': 'warn', 'message': 'memory dir missing'}

    total = len(list(mem_dir.rglob('*.md')))
    return {
        'status': 'ok' if total > 0 else 'warn',
        'total_files': total,
    }

def check_failures():
    """Check recent tool failures."""
    fail_log = CLAUDE / '.claude' / 'tool_failures' / 'failures.jsonl'
    if not fail_log.exists():
        return {'status': 'ok', 'recent': 0}

    recent = 0
    cutoff = datetime.now() - timedelta(hours=24)
    for line in fail_log.read_text(encoding='utf-8', errors='ignore').split('\n'):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry.get('timestamp', ''))
            if ts > cutoff:
                recent += 1
        except Exception:
            pass

    return {
        'status': 'ok' if recent < 5 else ('warn' if recent < 10 else 'critical'),
        'recent_24h': recent,
    }

def check_strategy():
    """Check current evolution strategy."""
    strat_file = CLAUDE / 'session-env' / 'evolve-strategy.txt'
    strategy = 'balanced'  # default
    if strat_file.exists():
        for line in strat_file.read_text().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                strategy = line
                break
    return {'strategy': strategy}

def main():
    results = {
        'timestamp': datetime.now().isoformat(),
        'disk': check_disk(),
        'git': check_git(),
        'hooks': check_hooks(),
        'evolution': check_evolution(),
        'memory': check_memory(),
        'failures': check_failures(),
        'strategy': check_strategy(),
    }

    # Overall health
    statuses = [v.get('status', 'ok') for v in results.values() if isinstance(v, dict)]
    criticals = statuses.count('critical')
    warns = statuses.count('warn')
    if criticals:
        results['overall'] = 'critical'
    elif warns > 2:
        results['overall'] = 'warn'
    else:
        results['overall'] = 'ok'

    if '--json' in sys.argv:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"Health: {results['overall'].upper()}")
        print(f"  Disk:    {results['disk'].get('free_gb','?')}GB free / {results['disk'].get('total_gb','?')}GB total")
        print(f"  Git:     {results['git'].get('dirty_files',0)} dirty files, last: {results['git'].get('last_commit','?')}")
        print(f"  Hooks:   {results['hooks']['total']} scripts, {len(results['hooks']['heavy'])} heavy (>200 lines)")
        for h in results['hooks']['heavy']:
            print(f"           - {h['name']}: {h['lines']} lines")
        print(f"  Memory:  {results['memory'].get('total_files',0)} files")
        print(f"  Failures:{results['failures'].get('recent_24h',0)} in 24h")

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
