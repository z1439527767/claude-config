#!/usr/bin/env python3
"""orchestrator — Ralph's dispatch and coordination center.
Usage:
  python3 orchestrator.py dispatch guard verify_diff '{"base": "HEAD~1"}'
  python3 orchestrator.py dispatch memory pack_finding '{"text": "..."}'
  python3 orchestrator.py dispatch build implement '{"task": "create X"}'
  python3 orchestrator.py dispatch watch health_check
  python3 orchestrator.py dispatch learn research '{"query": "..."}'
  python3 orchestrator.py dispatch plan decompose '{"goal": "..."}'
  python3 orchestrator.py status                    — Check all agents
  python3 orchestrator.py sweep                     — Run Watch → Learn → Memory cycle
  python3 orchestrator.py precommit                 — Guard + Watch before commit
  python3 orchestrator.py handoff                   — Plan + Memory for session handoff
"""
import sys, json, os, io, uuid
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
BB_DIR = CLAUDE / 'blackboard'
TEAM_FILE = CLAUDE / '.claude' / 'agents' / 'team.json'

def load_team():
    if TEAM_FILE.exists():
        return json.loads(TEAM_FILE.read_text(encoding='utf-8'))
    return None

def ensure_blackboard():
    """Ensure blackboard directory structure exists."""
    for agent in ["guard", "memory", "build", "watch", "learn", "plan"]:
        for sub in ["inbox", "outbox"]:
            (BB_DIR / agent / sub).mkdir(parents=True, exist_ok=True)

def create_task(agent, action, payload=None):
    """Create a task in an agent's inbox."""
    task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "from": "orchestrator",
        "to": agent,
        "action": action,
        "payload": payload or {},
        "priority": "medium",
        "created": datetime.now().isoformat(),
        "status": "dispatched",
    }
    inbox_dir = BB_DIR / agent / "inbox"
    task_file = inbox_dir / f"{task_id}.json"
    task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
    return task

def read_result(agent, task_id=None):
    """Read results from an agent's outbox."""
    outbox = BB_DIR / agent / "outbox"
    if task_id:
        result_file = outbox / f"{task_id}.json"
        if result_file.exists():
            return json.loads(result_file.read_text(encoding='utf-8'))
        return None

    # Return all results, newest first
    results = []
    for f in sorted(outbox.glob("task-*.json"), reverse=True):
        try:
            results.append(json.loads(f.read_text(encoding='utf-8')))
        except Exception:
            pass
    return results

def update_status(agent_states=None):
    """Update the global status file."""
    status = {
        "updated": datetime.now().isoformat(),
        "agents": agent_states or {},
    }
    (BB_DIR / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')

def cmd_dispatch(args):
    """Dispatch a task to an agent."""
    if len(args) < 2:
        print("Usage: orchestrator.py dispatch <agent> <action> [payload_json]")
        return

    agent = args[0]
    action = args[1]
    payload = json.loads(args[2]) if len(args) > 2 else {}

    team = load_team()
    if team and agent not in team.get("agents", {}):
        print(f"Unknown agent: {agent}. Available: {list(team.get('agents', {}).keys())}")
        return

    ensure_blackboard()
    task = create_task(agent, action, payload)

    agent_info = team.get("agents", {}).get(agent, {}) if team else {}
    emoji = agent_info.get("emoji", "🤖")
    print(f"{emoji} DISPATCHED: {task['id']}")
    print(f"   to: {agent} ({agent_info.get('role', 'unknown')})")
    print(f"   action: {action}")
    print(f"   inbox: blackboard/{agent}/inbox/{task['id']}.json")
    print(f"   Next: agent should read task, execute, write result to outbox/")

def cmd_status(args):
    """Check status of all agents."""
    ensure_blackboard()
    team = load_team()

    print("AGENT STATUS")
    print("=" * 50)

    for agent in ["guard", "memory", "build", "watch", "learn", "plan"]:
        info = team.get("agents", {}).get(agent, {}) if team else {}
        emoji = info.get("emoji", "🤖")
        role = info.get("role", agent)

        # Count inbox/outbox
        inbox_count = len(list((BB_DIR / agent / "inbox").glob("*.json"))) if (BB_DIR / agent / "inbox").exists() else 0
        outbox_count = len(list((BB_DIR / agent / "outbox").glob("*.json"))) if (BB_DIR / agent / "outbox").exists() else 0

        print(f"{emoji} {agent:<10} {role:<35} inbox:{inbox_count} outbox:{outbox_count}")

    # Check overall status
    status_file = BB_DIR / "status.json"
    if status_file.exists():
        s = json.loads(status_file.read_text(encoding='utf-8'))
        print(f"\nLast update: {s.get('updated', 'unknown')}")

def cmd_sweep(args):
    """Periodic sweep: Watch → Learn → Memory."""
    print("SWEEP: running health → learning → memory cycle")
    ensure_blackboard()

    # 1. Watch: health check
    print("1/3 Watch: health check...")
    create_task("watch", "health_check", {"mode": "quick"})
    print("   → dispatched to Watch")

    # 2. Learn: extract heuristics from recent activity
    print("2/3 Learn: heuristic extraction...")
    create_task("learn", "extract_heuristics", {"since": "7d"})
    print("   → dispatched to Learn")

    # 3. Memory: consolidate
    print("3/3 Memory: consolidation...")
    create_task("memory", "consolidate", {"mode": "auto"})
    print("   → dispatched to Memory")

    print("SWEEP: all dispatched. Check outbox/ for results.")

def cmd_precommit(args):
    """Pre-commit check: Guard + Watch."""
    print("PRECOMMIT: guard + watch verification")
    ensure_blackboard()

    create_task("guard", "verify_diff", {"base": "HEAD~1"})
    create_task("watch", "health_check", {"mode": "quick"})
    print("   → Guard + Watch dispatched in parallel")

def cmd_handoff(args):
    """Session handoff: Plan + Memory."""
    print("HANDOFF: plan + memory for session continuity")
    ensure_blackboard()

    create_task("plan", "summarize_session", {"mode": "handoff"})
    create_task("memory", "pack_session", {"mode": "auto"})
    print("   → Plan + Memory dispatched in parallel")

def main():
    ensure_blackboard()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    handlers = {
        "dispatch": cmd_dispatch,
        "status": cmd_status,
        "sweep": cmd_sweep,
        "precommit": cmd_precommit,
        "handoff": cmd_handoff,
    }

    if cmd in handlers:
        handlers[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print("Use: dispatch, status, sweep, precommit, handoff")

if __name__ == "__main__":
    main()
