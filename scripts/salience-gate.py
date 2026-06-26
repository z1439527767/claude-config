#!/usr/bin/env python3
"""salience-gate — Ralph's thalamic attention filter.
Like the brain's thalamus, filters 99% of incoming information before it reaches
consciousness. Only high-salience signals pass through.

Three filter layers:
  L1: Relevance Gate    — Is this relevant to current task/project?
  L2: Novelty Gate      — Is this new information or already known?
  L3: Urgency Gate      — Does this need attention NOW or can it wait?

Uses adaptive thresholds that adjust based on context pressure and task load.

Usage:
  python3 salience-gate.py --input "error message"        # Score a single input
  python3 salience-gate.py --batch <file.json>            # Score multiple inputs
  python3 salience-gate.py --threshold                    # Show current thresholds
  python3 salience-gate.py --inject                       # Salience context for consciousness
"""
import sys, json, os, io, re, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
GATE_STATE = CLAUDE / '.claude' / 'salience_state.json'
MEMORY_DIR = CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'
BLACKBOARD = CLAUDE / 'blackboard' / 'salience'
BLACKBOARD.mkdir(parents=True, exist_ok=True)

# ── Signal Categories ──
SIGNAL_TYPES = {
    "error":       {"base_salience": 0.9, "urgency": "high",   "decay_hours": 2},
    "security":    {"base_salience": 0.95, "urgency": "critical", "decay_hours": 0.5},
    "user_input":  {"base_salience": 0.8, "urgency": "high",   "decay_hours": 1},
    "tool_output": {"base_salience": 0.4, "urgency": "normal", "decay_hours": 4},
    "system_event":{"base_salience": 0.5, "urgency": "normal", "decay_hours": 6},
    "insight":     {"base_salience": 0.7, "urgency": "low",    "decay_hours": 24},
    "noise":       {"base_salience": 0.1, "urgency": "low",    "decay_hours": 1},
}

# ── Known Patterns (familiar = lower salience) ──
KNOWN_PATTERNS = set()

def load_known_patterns():
    """Load patterns that are already known (reduce novelty salience)."""
    global KNOWN_PATTERNS
    if not MEMORY_DIR.exists():
        return
    for mf in MEMORY_DIR.rglob("*.md"):
        if mf.name == "MEMORY.md":
            continue
        try:
            content = mf.read_text(encoding='utf-8')
            desc_match = re.search(r'description:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            if desc_match:
                sig = hashlib.sha256(desc_match.group(1).lower().encode()).hexdigest()[:16]
                KNOWN_PATTERNS.add(sig)
        except Exception:
            pass

def load_gate_state():
    if GATE_STATE.exists():
        try:
            return json.loads(GATE_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "thresholds": {"relevance": 0.3, "novelty": 0.2, "urgency": 0.5},
        "filtered_count": 0,
        "passed_count": 0,
        "context_pressure": 0.0,  # 0.0-1.0, how full is context
        "task_load": 0.0,         # 0.0-1.0, how busy is the agent
        "history": [],
    }

def save_gate_state(state):
    GATE_STATE.parent.mkdir(parents=True, exist_ok=True)
    state["history"] = state["history"][-100:]  # Keep last 100
    GATE_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

# ── L1: Relevance Gate ──

def score_relevance(signal, current_task=None):
    """How relevant is this signal to what we're doing right now?"""
    text = signal.get("text", "").lower()
    signal_type = signal.get("type", "noise")

    # Base relevance by type
    base = SIGNAL_TYPES.get(signal_type, SIGNAL_TYPES["noise"])["base_salience"]

    # Boost: matches current task keywords
    if current_task:
        task_words = set(re.findall(r'\b\w{3,}\b', current_task.lower()))
        signal_words = set(re.findall(r'\b\w{3,}\b', text))
        overlap = task_words & signal_words
        if overlap:
            base += min(0.3, len(overlap) * 0.05)

    # Boost: contains actionable keywords
    action_keywords = {'error', 'fail', 'fix', 'bug', 'security', 'crash', 'leak', 'broken',
                       'timeout', 'denied', 'blocked', 'missing', 'invalid', 'critical'}
    if any(kw in text for kw in action_keywords):
        base += 0.15

    # Penalty: low-signal content
    low_signal = {'ok', 'done', 'success', 'completed', '...', '---', '==='}
    if all(w in low_signal for w in text.split()[:5]):
        base *= 0.3

    return min(1.0, max(0.0, base))

# ── L2: Novelty Gate ──

def score_novelty(signal):
    """Is this new information or something we've seen before?"""
    text = signal.get("text", "").lower()
    sig = hashlib.sha256(text[:200].encode()).hexdigest()[:16]

    # Exact match = seen before, very low novelty
    if sig in KNOWN_PATTERNS:
        return 0.05

    # Partial match = familiar pattern
    words = set(re.findall(r'\b\w{4,}\b', text))
    known_count = sum(1 for w in words if w in str(KNOWN_PATTERNS))
    if len(words) > 0 and known_count / len(words) > 0.5:
        return 0.2

    # Completely new = high novelty
    return 0.8

# ── L3: Urgency Gate ──

def score_urgency(signal, context_pressure=0.0):
    """Does this need attention NOW?"""
    signal_type = signal.get("type", "noise")
    base_urgency = SIGNAL_TYPES.get(signal_type, SIGNAL_TYPES["noise"])["urgency"]

    urgency_map = {"critical": 1.0, "high": 0.8, "normal": 0.4, "low": 0.1}
    score = urgency_map.get(base_urgency, 0.3)

    # Time pressure boost: if context is full, raise urgency for important things
    if context_pressure > 0.8 and score > 0.5:
        score += 0.15

    # Decay: old signals lose urgency
    ts = signal.get("timestamp")
    if ts:
        try:
            age_hours = (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 3600
            decay_hours = SIGNAL_TYPES.get(signal_type, {"decay_hours": 1})["decay_hours"]
            score *= max(0.1, 1 - age_hours / decay_hours)
        except Exception:
            pass

    return min(1.0, score)


# ── Combined Gate ──

def evaluate_signal(signal, state, current_task=None):
    """Run a signal through all three gates. Returns (passed, score, reason)."""
    # Adaptive thresholds based on context pressure
    thresholds = state["thresholds"].copy()
    cp = state.get("context_pressure", 0.0)
    if cp > 0.8:
        # Under high pressure, raise thresholds — be more selective
        thresholds["relevance"] = min(0.8, thresholds["relevance"] * 2)
        thresholds["novelty"] = min(0.7, thresholds["novelty"] * 2)

    rel = score_relevance(signal, current_task)
    nov = score_novelty(signal)
    urg = score_urgency(signal, cp)

    # Combined salience score (weighted)
    salience = rel * 0.4 + nov * 0.3 + urg * 0.3

    # Gate check
    passed = (
        rel >= thresholds["relevance"] and
        nov >= thresholds["novelty"] and
        urg >= thresholds["urgency"]
    )

    reasons = []
    if rel < thresholds["relevance"]:
        reasons.append(f"relevance={rel:.2f}<{thresholds['relevance']:.2f}")
    if nov < thresholds["novelty"]:
        reasons.append(f"novelty={nov:.2f}<{thresholds['novelty']:.2f}")
    if urg < thresholds["urgency"]:
        reasons.append(f"urgency={urg:.2f}<{thresholds['urgency']:.2f}")

    return {
        "passed": passed,
        "salience": round(salience, 2),
        "relevance": round(rel, 2),
        "novelty": round(nov, 2),
        "urgency": round(urg, 2),
        "thresholds": {k: round(v, 2) for k, v in thresholds.items()},
        "reason": "; ".join(reasons) if reasons else "all gates passed",
        "action": "CONSCIOUS" if passed else "filtered",
    }


# ── Adaptive Threshold Tuning ──

def adapt_thresholds(state):
    """Adjust thresholds based on recent filter patterns."""
    history = state.get("history", [])
    if len(history) < 10:
        return state

    recent = history[-20:]
    pass_rate = sum(1 for h in recent if h.get("passed")) / len(recent)

    # If passing too many signals, raise thresholds
    if pass_rate > 0.8:
        state["thresholds"]["relevance"] = min(0.8, state["thresholds"]["relevance"] + 0.05)
        state["thresholds"]["novelty"] = min(0.7, state["thresholds"]["novelty"] + 0.03)
    # If filtering too many, lower thresholds
    elif pass_rate < 0.1:
        state["thresholds"]["relevance"] = max(0.1, state["thresholds"]["relevance"] - 0.05)
        state["thresholds"]["novelty"] = max(0.05, state["thresholds"]["novelty"] - 0.03)

    return state


# ── Context Pressure Estimation ──

def estimate_context_pressure():
    """Estimate how 'full' the agent's context is."""
    pressure = 0.0
    signals = 0

    # Check CLAUDE.md + rules token load
    claude_md = CLAUDE / 'CLAUDE.md'
    if claude_md.exists():
        size = claude_md.stat().st_size
        pressure += min(0.3, size / 50000)  # 50KB = 0.3 contribution
        signals += 1

    rules_dir = CLAUDE / '.claude' / 'rules'
    if rules_dir.exists():
        total = sum(f.stat().st_size for f in rules_dir.glob("*.md"))
        pressure += min(0.3, total / 100000)
        signals += 1

    mem_index = MEMORY_DIR / 'MEMORY.md'
    if mem_index.exists():
        pressure += min(0.2, mem_index.stat().st_size / 30000)
        signals += 1

    # Tool count contributes
    scripts_dir = CLAUDE / 'scripts'
    if scripts_dir.exists():
        tool_count = len(list(scripts_dir.glob("*.py")))
        pressure += min(0.2, tool_count / 200)
        signals += 1

    return round(min(1.0, pressure / max(1, signals) * 2), 2)


# ── Inject for Consciousness ──

def salience_inject(state, max_tokens=150):
    """Generate compact salience status for context injection."""
    cp = estimate_context_pressure()
    state["context_pressure"] = cp
    save_gate_state(state)

    passed = state.get("passed_count", 0)
    filtered = state.get("filtered_count", 0)
    total = passed + filtered

    t = state["thresholds"]
    lines = [
        "## Salience Gate (attention filter)",
        f"- Context pressure: {cp:.0%} | Pass rate: {passed}/{total} ({passed/max(1,total):.0%})",
        f"- Thresholds: R≥{t['relevance']:.2f} N≥{t['novelty']:.2f} U≥{t['urgency']:.2f}",
    ]
    if cp > 0.8:
        lines.append("- ⚠️ High pressure — filtering aggressively")
    elif cp < 0.3:
        lines.append("- 🟢 Low pressure — receptive to new signals")
    return '\n'.join(lines)


def main():
    load_known_patterns()
    state = load_gate_state()
    cp = estimate_context_pressure()
    state["context_pressure"] = cp

    if "--threshold" in sys.argv:
        print(f"SALIENCE GATE THRESHOLDS:")
        print(f"  Relevance:  ≥ {state['thresholds']['relevance']:.2f}")
        print(f"  Novelty:    ≥ {state['thresholds']['novelty']:.2f}")
        print(f"  Urgency:    ≥ {state['thresholds']['urgency']:.2f}")
        print(f"  Pressure:   {cp:.0%}")
        print(f"  Pass rate:  {state['passed_count']}/{state['passed_count'] + state['filtered_count']}")
        return

    if "--inject" in sys.argv:
        print(salience_inject(state))
        return

    if "--reset" in sys.argv:
        state["thresholds"] = {"relevance": 0.3, "novelty": 0.2, "urgency": 0.5}
        state["filtered_count"] = 0
        state["passed_count"] = 0
        save_gate_state(state)
        print("SALIENCE GATE: Reset to defaults")
        return

    # Evaluate input signal
    if "--input" in sys.argv:
        idx = sys.argv.index("--input")
        if idx + 1 < len(sys.argv):
            text = sys.argv[idx + 1]
            signal = {"text": text, "type": "user_input", "timestamp": datetime.now().isoformat()}
        else:
            print("Usage: --input 'signal text'")
            return
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        signal = {"text": text, "type": "tool_output", "timestamp": datetime.now().isoformat()}
    else:
        # Default: show status
        print(f"SALIENCE GATE: {state['passed_count']} passed, {state['filtered_count']} filtered")
        print(f"  Pressure: {cp:.0%} | Thresholds: R≥{state['thresholds']['relevance']:.2f} N≥{state['thresholds']['novelty']:.2f}")
        return

    result = evaluate_signal(signal, state)
    result["signal"] = text[:100]

    # Update state
    if result["passed"]:
        state["passed_count"] += 1
    else:
        state["filtered_count"] += 1
    state["history"].append(result)
    state = adapt_thresholds(state)
    save_gate_state(state)

    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        icon = "🟢" if result["passed"] else "🔴"
        print(f"{icon} [{result['action']}] salience={result['salience']:.2f}")
        print(f"   R={result['relevance']:.2f} N={result['novelty']:.2f} U={result['urgency']:.2f}")
        if result["reason"] != "all gates passed":
            print(f"   Blocked: {result['reason']}")

if __name__ == "__main__":
    main()
