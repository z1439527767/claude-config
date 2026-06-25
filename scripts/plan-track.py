#!/usr/bin/env python3
"""plan-track — Codex update_plan equivalent. Step tracking with pending/in_progress/completed.
Usage:
  python3 plan-track.py init "Build auth system"           # Create new plan
  python3 plan-track.py step "Add JWT token verification"   # Add a step
  python3 plan-track.py start 1                             # Mark step 1 as in_progress
  python3 plan-track.py done 1                              # Mark step 1 as completed
  python3 plan-track.py status                              # Show current plan state
  python3 plan-track.py reset                               # Clear current plan
  python3 plan-track.py inject                              # Print ~150 token status preamble

State file: ~/.claude/session-env/plan_state.json
Survives context compaction. Enforces exactly one in_progress step.
"""
import sys, json, os, io
from pathlib import Path
from datetime import datetime

# Fix UnicodeEncodeError on Windows (emoji in output)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
STATE_FILE = HOME / '.claude' / 'session-env' / 'plan_state.json'

def load():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"goal": "", "steps": [], "created": "", "updated": ""}

def save(state):
    state["updated"] = datetime.now().isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def cmd_init(state, args):
    goal = " ".join(args[1:]) if len(args) > 1 else "Untitled Plan"
    state["goal"] = goal
    state["steps"] = []
    state["created"] = datetime.now().isoformat()
    save(state)
    print(f"PLAN: '{goal}' — ready. Add steps with: plan-track step <description>")

def cmd_step(state, args):
    if not state["goal"]:
        print("PLAN: no active plan. Use 'plan-track init <goal>' first.")
        return
    desc = " ".join(args[1:]) if len(args) > 1 else "Unnamed step"
    step = {
        "id": len(state["steps"]) + 1,
        "description": desc,
        "status": "pending",
        "added": datetime.now().isoformat()
    }
    state["steps"].append(step)
    save(state)
    print(f"PLAN: step {step['id']} added — '{desc}' [{step['status']}]")

def cmd_start(state, args):
    if len(args) < 2:
        print("PLAN: specify step ID or number. Usage: plan-track start <id>")
        return
    step_id = int(args[1])
    # Set all steps with status 'in_progress' to 'pending' first
    for s in state["steps"]:
        if s["status"] == "in_progress":
            s["status"] = "pending"
    # Set target step to in_progress
    for s in state["steps"]:
        if s["id"] == step_id:
            s["status"] = "in_progress"
            save(state)
            print(f"PLAN: step {step_id} now in_progress — '{s['description']}'")
            return
    print(f"PLAN: step {step_id} not found. Total steps: {len(state['steps'])}")

def cmd_done(state, args):
    if len(args) < 2:
        print("PLAN: specify step ID. Usage: plan-track done <id>")
        return
    step_id = int(args[1])
    for s in state["steps"]:
        if s["id"] == step_id:
            s["status"] = "completed"
            save(state)
            remaining = sum(1 for x in state["steps"] if x["status"] != "completed")
            print(f"PLAN: step {step_id} completed — '{s['description']}' ({remaining} remaining)")
            if remaining == 0:
                print("PLAN: ALL DONE")
            return
    print(f"PLAN: step {step_id} not found.")

def cmd_status(state, args=None):
    if not state["goal"]:
        print("PLAN: no active plan.")
        return
    total = len(state["steps"])
    done = sum(1 for s in state["steps"] if s["status"] == "completed")
    in_prog = [s for s in state["steps"] if s["status"] == "in_progress"]
    pending = sum(1 for s in state["steps"] if s["status"] == "pending")

    print(f"PLAN: {state['goal']}")
    print(f"      {done}/{total} done, {pending} pending")
    if in_prog:
        print(f"      NOW: [{in_prog[0]['id']}] {in_prog[0]['description']}")

    for s in state["steps"]:
        icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}.get(s["status"], "  ")
        print(f"  {icon} [{s['id']}] {s['description']}")

def cmd_inject(state, args=None):
    """Print ~150 token status preamble for context injection. Prevents drift."""
    if not state["goal"]:
        return
    total = len(state["steps"])
    done = sum(1 for s in state["steps"] if s["status"] == "completed")
    in_prog = [s for s in state["steps"] if s["status"] == "in_progress"]
    pending_names = [s["description"] for s in state["steps"] if s["status"] == "pending"]

    lines = [f"Goal: {state['goal']}. Done: {done}/{total}."]
    if in_prog:
        lines.append(f"Current: {in_prog[0]['description']}.")
    if pending_names:
        lines.append(f"Remaining: {'; '.join(pending_names[:5])}.")
    print(" ".join(lines))

def cmd_reset(state, args=None):
    STATE_FILE.unlink(missing_ok=True)
    print("PLAN: reset.")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    state = load()

    handlers = {
        "init": cmd_init, "step": cmd_step, "start": cmd_start,
        "done": cmd_done, "status": cmd_status, "inject": cmd_inject,
        "reset": cmd_reset,
    }

    if cmd in handlers:
        handlers[cmd](state, sys.argv[1:])
    else:
        print(f"Unknown command: {cmd}. Use: init step start done status inject reset")

if __name__ == "__main__":
    main()
