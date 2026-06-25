#!/usr/bin/env python3
"""neuromodulation — Ralph's reward/punishment learning system.
Like the brain's neuromodulatory systems, reinforces good behaviors and suppresses bad ones.

Three neuromodulators:
  Dopamine (DA)     — Reward prediction error. "That worked better than expected → do it again."
  Serotonin (5-HT)  — Patience & delayed gratification. "Wait. Long-term value > short-term gain."
  Norepinephrine (NE) — Arousal & urgency. "This is important. Pay attention NOW."

Stores outcome→behavior mappings. Over time, good behaviors become automatic (intuition),
bad behaviors are suppressed (immune response).

Usage:
  python3 neuromodulation.py --outcome "success" --action "used Edit not Write" --context "..."
  python3 neuromodulation.py --learn                           # Process recent outcomes
  python3 neuromodulation.py --stats                           # Show neuromodulator levels
  python3 neuromodulation.py --inject                          # Context injection
  python3 neuromodulation.py --reinforce "tool_choice"         # Show reinforced behaviors
"""
import sys, json, os, io, re, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
NEURO_STATE = CLAUDE / '.claude' / 'neuromod_state.json'
OUTCOMES_FILE = CLAUDE / '.claude' / 'outcome_log.jsonl'

# ── Neuromodulator Models ──
# Each has: level (0-1), baseline, decay_rate, boost_triggers

NEURO_DEFAULTS = {
    "dopamine": {
        "level": 0.5, "baseline": 0.5, "decay_per_hour": 0.1,
        "boost_on": ["task_success", "positive_feedback", "tool_worked_first_try",
                      "learned_something_new", "solved_hard_problem"],
        "suppress_on": ["task_failure", "tool_error", "repeated_mistake", "user_correction"],
        "description": "Reward & motivation. High=explore, Low=conservative."
    },
    "serotonin": {
        "level": 0.6, "baseline": 0.6, "decay_per_hour": 0.05,
        "boost_on": ["long_term_plan_success", "patient_waiting_paid_off",
                      "deep_understanding", "elegant_solution"],
        "suppress_on": ["short_sighted_decision", "rushed_mistake",
                         "technical_debt_created", "ignored_warning"],
        "description": "Patience & long-term value. High=plan ahead, Low=impulsive."
    },
    "norepinephrine": {
        "level": 0.4, "baseline": 0.4, "decay_per_hour": 0.15,
        "boost_on": ["error_detected", "security_threat", "user_urgent",
                      "deadline_approaching", "unexpected_behavior"],
        "suppress_on": ["routine_task", "low_priority", "all_quiet"],
        "description": "Arousal & vigilance. High=alert/anxious, Low=calm/relaxed."
    },
}

# ── Behavior Reinforcement Memory ──

def load_neuro_state():
    if NEURO_STATE.exists():
        try:
            return json.loads(NEURO_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "neuromodulators": {k: v.copy() for k, v in NEURO_DEFAULTS.items()},
        "reinforced_behaviors": {},  # behavior_hash → {count, successes, failures, weight}
        "outcome_count": 0,
        "last_update": None,
        "recent_events": [],
    }

def save_neuro_state(state):
    NEURO_STATE.parent.mkdir(parents=True, exist_ok=True)
    state["last_update"] = datetime.now().isoformat()
    state["recent_events"] = state["recent_events"][-50:]
    NEURO_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def log_outcome(action_type, outcome, context, detail=""):
    """Log an action→outcome pair for later learning."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "outcome": outcome,  # success, failure, partial, user_corrected
        "context": context[:300],
        "detail": detail[:200],
    }
    with open(OUTCOMES_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry

# ── Neuromodulator Update ──

def update_neuromodulators(state, event_type):
    """Update neuromodulator levels based on an event."""
    mods = state["neuromodulators"]

    for name, mod in mods.items():
        # Apply decay since last update
        last = state.get("last_update")
        if last:
            try:
                hours = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
                decay = mod["decay_per_hour"] * hours
                mod["level"] = mod["baseline"] + (mod["level"] - mod["baseline"]) * max(0, 1 - decay)
            except Exception:
                pass

        # Apply event boost/suppression
        if event_type in mod.get("boost_on", []):
            mod["level"] = min(1.0, mod["level"] + 0.15)
        elif event_type in mod.get("suppress_on", []):
            mod["level"] = max(0.0, mod["level"] - 0.1)

    return state

# ── Behavior Reinforcement ──

def reinforce_behavior(state, action_signature, outcome, context=""):
    """Reinforce or suppress a behavior based on outcome."""
    rb = state["reinforced_behaviors"]
    sig = hashlib.sha256(action_signature.encode()).hexdigest()[:12]

    if sig not in rb:
        rb[sig] = {
            "signature": action_signature[:120],
            "count": 0,
            "successes": 0,
            "failures": 0,
            "weight": 0.0,           # -1.0 (avoid) to +1.0 (prefer)
            "last_outcome": None,
            "contexts": [],
        }

    entry = rb[sig]
    entry["count"] += 1
    if outcome == "success":
        entry["successes"] += 1
    else:
        entry["failures"] += 1

    # Update weight using exponential moving average
    recent = 1.0 if outcome == "success" else -1.0
    entry["weight"] = entry["weight"] * 0.8 + recent * 0.2
    entry["last_outcome"] = outcome
    entry["contexts"].append(context[:100])
    entry["contexts"] = entry["contexts"][-5:]

    return state


# ── Process Recent Outcomes ──

def process_recent_outcomes(state, limit=50):
    """Process recent outcome logs and update neuromodulators + reinforcement."""
    if not os.path.exists(OUTCOMES_FILE):
        return state

    # Read recent outcomes
    outcomes = []
    with open(OUTCOMES_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                outcomes.append(json.loads(line))
            except Exception:
                pass

    recent = outcomes[-limit:]

    for outcome in reversed(recent):
        action_type = outcome.get("action_type", "")
        result = outcome.get("outcome", "")
        context = outcome.get("context", "")

        # Update neuromodulators
        if result == "success":
            state = update_neuromodulators(state, "task_success")
        elif result == "failure":
            state = update_neuromodulators(state, "task_failure")
        elif result == "user_corrected":
            state = update_neuromodulators(state, "user_correction")

        # Reinforce behavior
        action_sig = f"{action_type}:{context[:80]}"
        state = reinforce_behavior(state, action_sig, result, context)

    state["outcome_count"] = len(outcomes)
    state["recent_events"] = [{"action": o["action_type"], "outcome": o["outcome"],
                                "ts": o["timestamp"][:19]} for o in recent[-10:]]
    return state


# ── Get Top Reinforced/Avoided Behaviors ──

def get_top_behaviors(state, n=5):
    """Get most reinforced and most suppressed behaviors."""
    rb = state.get("reinforced_behaviors", {})
    if not rb:
        return [], []

    sorted_behaviors = sorted(rb.values(), key=lambda b: -b["weight"])
    preferred = [b for b in sorted_behaviors if b["weight"] > 0.3 and b["count"] >= 2][:n]
    avoided = [b for b in sorted_behaviors if b["weight"] < -0.3 and b["count"] >= 2][:n]

    return preferred, avoided


# ── Inject ──

def neuro_inject(state, max_tokens=150):
    """Generate neuromodulation status for context injection."""
    mods = state["neuromodulators"]
    preferred, avoided = get_top_behaviors(state, 3)

    lines = ["## Neuromodulation (reward learning)"]

    # Neuromodulator levels as emoji bars
    for name, mod in mods.items():
        level = mod["level"]
        bar = "█" * int(level * 10) + "░" * (10 - int(level * 10))
        emoji = {"dopamine": "🎯", "serotonin": "🧘", "norepinephrine": "⚡"}.get(name, "💊")
        lines.append(f"- {emoji} {name:15s} [{bar}] {level:.0%}")

    if preferred:
        lines.append("- ✅ Preferred behaviors:")
        for b in preferred[:2]:
            lines.append(f"  · {b['signature'][:80]} ({b['successes']}/{b['count']})")

    if avoided:
        lines.append("- ❌ Avoided behaviors:")
        for b in avoided[:2]:
            lines.append(f"  · {b['signature'][:80]} ({b['failures']}/{b['count']})")

    return '\n'.join(lines)


def main():
    state = load_neuro_state()

    if "--outcome" in sys.argv and "--action" in sys.argv:
        outcome_idx = sys.argv.index("--outcome")
        action_idx = sys.argv.index("--action")
        outcome = sys.argv[outcome_idx + 1] if outcome_idx + 1 < len(sys.argv) else "success"
        action = sys.argv[action_idx + 1] if action_idx + 1 < len(sys.argv) else "unknown"
        context = ""
        if "--context" in sys.argv:
            ci = sys.argv.index("--context")
            if ci + 1 < len(sys.argv):
                context = sys.argv[ci + 1]

        entry = log_outcome("user_reported", outcome, context, action)
        state = reinforce_behavior(state, action, outcome, context)
        state = update_neuromodulators(state, f"task_{outcome}")
        save_neuro_state(state)
        print(f"NEUROMOD: {outcome} → {action[:80]}")
        return

    if "--learn" in sys.argv:
        state = process_recent_outcomes(state)
        save_neuro_state(state)
        mods = state["neuromodulators"]
        print(f"NEUROMOD: Learned from {state['outcome_count']} outcomes")
        for name, mod in mods.items():
            print(f"  {name}: {mod['level']:.0%} (baseline={mod['baseline']:.0%})")
        return

    if "--stats" in sys.argv:
        mods = state["neuromodulators"]
        preferred, avoided = get_top_behaviors(state)
        print("NEUROMODULATOR LEVELS:")
        for name, mod in mods.items():
            bar = "█" * int(mod["level"] * 20) + "░" * (20 - int(mod["level"] * 20))
            print(f"  {name:20s} [{bar}] {mod['level']:.0%} — {mod['description']}")
        if preferred:
            print(f"\nREINFORCED (weight > 0.3):")
            for b in preferred:
                print(f"  ✅ {b['signature'][:80]} (w={b['weight']:.2f}, {b['successes']}/{b['count']})")
        if avoided:
            print(f"\nSUPPRESSED (weight < -0.3):")
            for b in avoided:
                print(f"  ❌ {b['signature'][:80]} (w={b['weight']:.2f}, {b['failures']}/{b['count']})")
        return

    if "--inject" in sys.argv:
        print(neuro_inject(state))
        return

    if "--reinforce" in sys.argv:
        preferred, avoided = get_top_behaviors(state, 10)
        print("REINFORCED BEHAVIORS:")
        for b in preferred:
            print(f"  +{b['weight']:.2f} {b['signature'][:100]}")
        print("\nAVOIDED BEHAVIORS:")
        for b in avoided:
            print(f"  {b['weight']:.2f} {b['signature'][:100]}")
        return

    # Default
    print("neuromodulation: --outcome ... --action ... | --learn | --stats | --inject | --reinforce")

if __name__ == "__main__":
    main()
