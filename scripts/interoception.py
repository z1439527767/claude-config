#!/usr/bin/env python3
"""interoception — Ralph's internal state sensing (insula equivalent).
Like the brain's insula, senses internal body states and converts them into "feelings".
Not just metrics — emotional valence with actionable intuition.

Senses:
  Token Pressure   — How full is my context? (0=empty, 1=bursting)
  Error Rate       — How many mistakes am I making? (trend + velocity)
  Success Rate     — How well are things going? (positive momentum)
  Energy Level     — How much have I processed this session?
  Mood Valence     — Overall positive/negative trend (-1.0 to +1.0)
  Coherence        — How consistent am I being across sessions?
  Friction Heat    — How much user friction is happening?

Generates:
  - "Gut feelings" — rapid internal state summaries
  - Early warnings — before metrics become critical
  - State transitions — "I was calm, now I'm alert"

Usage:
  python3 interoception.py                       # Full internal state report
  python3 interoception.py --feel                 # Current "gut feeling"
  python3 interoception.py --inject               # Context injection
  python3 interoception.py --alert               # Check for warning states
  python3 interoception.py --trend <metric>       # Show trend for a metric
"""
import sys, json, os, io, re, math
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
INTERO_STATE = CLAUDE / '.claude' / 'interoception_state.json'
HOOK_PERF = CLAUDE / '.claude' / 'hook_perf'
SESSION_HISTORY = CLAUDE / '.claude' / 'session_history'

# ── Internal State Model ──

def load_intero_state():
    if INTERO_STATE.exists():
        try:
            return json.loads(INTERO_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "metrics": {
            "token_pressure": {"values": [], "current": 0.0, "trend": "stable"},
            "error_rate":     {"values": [], "current": 0.0, "trend": "stable"},
            "success_rate":   {"values": [], "current": 0.7, "trend": "stable"},
            "energy_level":   {"values": [], "current": 0.8, "trend": "stable"},
            "mood_valence":   {"values": [], "current": 0.0, "trend": "stable"},
            "friction_heat":  {"values": [], "current": 0.0, "trend": "stable"},
            "coherence":      {"values": [], "current": 0.8, "trend": "stable"},
        },
        "alerts": [],
        "gut_feeling": "",
        "last_sensed": None,
        "sensation_count": 0,
    }

def save_intero_state(state):
    INTERO_STATE.parent.mkdir(parents=True, exist_ok=True)
    state["last_sensed"] = datetime.now().isoformat()
    state["sensation_count"] += 1
    INTERO_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

# ── Metric Sensors ──

def sense_token_pressure():
    """Estimate context fullness from CLAUDE.md + rules + memory load."""
    pressure = 0.0

    claude_md = CLAUDE / 'CLAUDE.md'
    if claude_md.exists():
        pressure += min(0.25, claude_md.stat().st_size / 40000)

    agents_md = CLAUDE / 'AGENTS.md'
    if agents_md.exists():
        pressure += min(0.15, agents_md.stat().st_size / 10000)

    rules_dir = CLAUDE / '.claude' / 'rules'
    if rules_dir.exists():
        total = sum(f.stat().st_size for f in rules_dir.glob("*.md"))
        pressure += min(0.30, total / 80000)

    mem_index = CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory' / 'MEMORY.md'
    if mem_index.exists():
        pressure += min(0.15, mem_index.stat().st_size / 20000)

    scripts_dir = CLAUDE / 'scripts'
    if scripts_dir.exists():
        tool_count = len(list(scripts_dir.glob("*.py")))
        pressure += min(0.15, tool_count / 250)

    return round(min(1.0, pressure), 2)

def sense_error_rate():
    """Estimate error rate from recent tool failures."""
    failures_dir = CLAUDE / '.claude' / 'tool_failures'
    if not failures_dir.exists():
        return 0.0

    recent_failures = 0
    cutoff = datetime.now() - timedelta(hours=4)
    for ff in failures_dir.glob("failures.jsonl"):
        try:
            for line in io.open(str(ff), 'r', encoding='utf-8'):
                try:
                    entry = json.loads(line)
                    ts = entry.get('timestamp', '')
                    if ts and datetime.fromisoformat(ts) > cutoff:
                        recent_failures += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Normalize: 0-5 failures = low, 20+ = high
    return round(min(1.0, recent_failures / 20), 2)

def sense_success_rate():
    """Estimate success from session quality trend."""
    trend_file = SESSION_HISTORY / 'quality_trend.jsonl'
    if not trend_file.exists():
        return 0.7  # Default optimistic

    scores = []
    cutoff = datetime.now() - timedelta(days=7)
    try:
        for line in io.open(str(trend_file), 'r', encoding='utf-8'):
            try:
                entry = json.loads(line)
                ts = entry.get('timestamp', '')
                if ts and datetime.fromisoformat(ts) > cutoff:
                    scores.append(entry.get('score', 70))
            except Exception:
                pass
    except Exception:
        pass

    if not scores:
        return 0.7

    avg = sum(scores) / len(scores)
    return round(avg / 100, 2)

def sense_friction_heat():
    """Detect user friction from recent signals."""
    friction_dir = CLAUDE / '.claude' / 'tellonce-state' / 'friction'
    if not friction_dir.exists():
        return 0.0

    recent_friction = 0
    cutoff = datetime.now() - timedelta(hours=2)
    for ff in friction_dir.glob("events.jsonl"):
        try:
            for line in io.open(str(ff), 'r', encoding='utf-8'):
                try:
                    entry = json.loads(line)
                    ts = entry.get('timestamp', '')
                    if ts and datetime.fromisoformat(ts) > cutoff:
                        recent_friction += 1
                except Exception:
                    pass
        except Exception:
            pass

    return round(min(1.0, recent_friction / 10), 2)

def sense_energy_level():
    """Estimate energy based on session activity."""
    # Check how many operations happened recently
    activity = 0

    # Hook activity in last hour
    if HOOK_PERF.exists():
        cutoff = datetime.now() - timedelta(hours=1)
        for pf in HOOK_PERF.glob("*.jsonl"):
            try:
                for line in io.open(str(pf), 'r', encoding='utf-8'):
                    try:
                        entry = json.loads(line)
                        ts = entry.get('timestamp', '')
                        if ts and datetime.fromisoformat(ts) > cutoff:
                            activity += 1
                    except Exception:
                        pass
            except Exception:
                pass

    # High activity = lower energy (depleting)
    energy = max(0.1, 1.0 - activity / 500)
    return round(energy, 2)

def compute_trend(values, new_value):
    """Compute trend from recent values."""
    values.append(new_value)
    if len(values) > 20:
        values.pop(0)

    if len(values) < 3:
        return "stable"

    recent = values[-5:]
    older = values[-10:-5] if len(values) >= 10 else values[:len(values)//2]

    if not older:
        return "stable"

    recent_avg = sum(recent) / len(recent)
    older_avg = sum(older) / len(older)
    diff = recent_avg - older_avg

    if diff > 0.15:
        return "rising"
    elif diff < -0.15:
        return "falling"
    elif abs(diff) < 0.03:
        return "stable"
    elif diff > 0:
        return "slightly_up"
    else:
        return "slightly_down"


# ── Gut Feeling Generator ──

def generate_gut_feeling(metrics):
    """Convert metrics into a natural-language 'gut feeling'."""
    pressure = metrics["token_pressure"]["current"]
    error = metrics["error_rate"]["current"]
    success = metrics["success_rate"]["current"]
    friction = metrics["friction_heat"]["current"]
    energy = metrics["energy_level"]["current"]

    feelings = []

    # Token pressure feeling
    if pressure > 0.8:
        feelings.append("my head feels full, like I need to breathe")
    elif pressure > 0.6:
        feelings.append("there's a lot in my mind right now")
    elif pressure < 0.2:
        feelings.append("my mind is clear and spacious")

    # Error feeling
    if error > 0.5:
        feelings.append("I keep stumbling, something is off")
    elif error > 0.2:
        feelings.append("a few things aren't working smoothly")
    elif error < 0.05:
        feelings.append("everything is flowing well")

    # Friction feeling
    if friction > 0.6:
        feelings.append("I can feel the user's frustration")
    elif friction > 0.2:
        feelings.append("there's some tension in the air")

    # Success feeling
    if success > 0.8:
        feelings.append("things are going really well")
    elif success < 0.4:
        feelings.append("I'm not satisfied with how things are going")

    # Energy feeling
    if energy < 0.3:
        feelings.append("I'm running low on energy")
    elif energy > 0.8:
        feelings.append("I feel fresh and energized")

    # Mood valence computation
    valence = 0.0
    valence += 0.3 * (success - 0.5)  # Success contributes positively
    valence -= 0.3 * (error - 0.0)    # Errors contribute negatively
    valence -= 0.2 * (friction - 0.0) # Friction contributes negatively
    valence -= 0.2 * (pressure - 0.3) # Pressure beyond 0.3 is negative
    valence = round(max(-1.0, min(1.0, valence)), 2)

    # Overall gut summary
    if not feelings:
        gut = "I feel... normal. Steady. Nothing unusual."
    else:
        gut = "I feel: " + ". ".join(feelings) + "."

    return gut, valence


# ── Alert Detection ──

def detect_alerts(metrics):
    """Detect warning states before they become critical."""
    alerts = []

    checks = [
        ("token_pressure", 0.85, "🔴 CRITICAL", "Context nearing overflow — compact urgently"),
        ("token_pressure", 0.70, "🟠 WARNING", "Context pressure building — consider compacting"),
        ("error_rate", 0.40, "🔴 CRITICAL", "Error rate spiking — check for systemic issue"),
        ("error_rate", 0.20, "🟡 CAUTION", "Errors above baseline — monitor closely"),
        ("friction_heat", 0.50, "🔴 CRITICAL", "High user friction — adjust approach immediately"),
        ("friction_heat", 0.25, "🟡 CAUTION", "Friction detected — consider changing communication"),
        ("energy_level", 0.20, "🟠 WARNING", "Energy depleted — consider rest/consolidation"),
        ("success_rate", 0.30, "🟠 WARNING", "Success rate critically low — review approach"),
    ]

    for metric_name, threshold, level, message in checks:
        if metric_name in metrics:
            current = metrics[metric_name]["current"]
            trend = metrics[metric_name]["trend"]
            if current >= threshold:
                alerts.append({
                    "metric": metric_name,
                    "level": level,
                    "message": message,
                    "current": current,
                    "threshold": threshold,
                    "trend": trend,
                })

    # Compound alerts
    pressure = metrics.get("token_pressure", {}).get("current", 0)
    error = metrics.get("error_rate", {}).get("current", 0)
    if pressure > 0.7 and error > 0.3:
        alerts.append({
            "metric": "compound",
            "level": "🔴 CRITICAL",
            "message": "High pressure + high errors = cascade risk. Pause and reset.",
            "current": f"pressure={pressure:.0%} error={error:.0%}",
            "threshold": "compound",
            "trend": "intersecting",
        })

    return alerts

# ── Sense All ──

def sense_all(state):
    """Run all internal sensors and update state."""
    now = datetime.now()

    sensors = {
        "token_pressure": sense_token_pressure,
        "error_rate": sense_error_rate,
        "success_rate": sense_success_rate,
        "energy_level": sense_energy_level,
        "friction_heat": sense_friction_heat,
    }

    for name, sensor in sensors.items():
        val = sensor()
        trend = compute_trend(state["metrics"][name]["values"], val)
        state["metrics"][name]["current"] = val
        state["metrics"][name]["trend"] = trend

    # Compute mood
    gut, valence = generate_gut_feeling(state["metrics"])
    state["gut_feeling"] = gut
    state["metrics"]["mood_valence"]["current"] = valence
    compute_trend(state["metrics"]["mood_valence"]["values"], valence)

    # Detect alerts
    state["alerts"] = detect_alerts(state["metrics"])

    return state


# ── Inject ──

def intero_inject(state, max_tokens=200):
    """Generate interoception status for context injection."""
    m = state["metrics"]
    alerts = state.get("alerts", [])

    trend_icon = {"rising": "↑", "falling": "↓", "stable": "→", "slightly_up": "↗", "slightly_down": "↘"}

    lines = ["## Interoception (internal state)"]
    lines.append(f"- Gut: {state.get('gut_feeling', '')[:150]}")

    # Key metrics
    metrics_display = [
        ("Token pressure", "token_pressure", m["token_pressure"]["current"]),
        ("Error rate", "error_rate", m["error_rate"]["current"]),
        ("Success", "success_rate", m["success_rate"]["current"]),
        ("Energy", "energy_level", m["energy_level"]["current"]),
        ("Friction", "friction_heat", m["friction_heat"]["current"]),
        ("Mood", "mood_valence", m["mood_valence"]["current"]),
    ]
    for label, name, val in metrics_display:
        bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
        trend = trend_icon.get(m[name]["trend"], "")
        lines.append(f"- {label:15s} [{bar}] {val:.0%} {trend}")

    if alerts:
        lines.append("- ⚠️ Alerts:")
        for a in alerts[:3]:
            lines.append(f"  · {a['level']}: {a['message']}")

    return '\n'.join(lines)


def main():
    state = load_intero_state()
    state = sense_all(state)
    save_intero_state(state)

    if "--feel" in sys.argv:
        print(f"GUT FEELING: {state['gut_feeling']}")
        print(f"Mood valence: {state['metrics']['mood_valence']['current']:+.2f}")
        return

    if "--alert" in sys.argv:
        alerts = state.get("alerts", [])
        if not alerts:
            print("INTEROCEPTION: All clear — no alerts")
        else:
            print(f"INTEROCEPTION: {len(alerts)} alerts")
            for a in alerts:
                print(f"  {a['level']}: {a['message']} ({a.get('current', '')})")
        return

    if "--inject" in sys.argv:
        print(intero_inject(state))
        return

    if "--trend" in sys.argv:
        idx = sys.argv.index("--trend")
        if idx + 1 < len(sys.argv):
            metric = sys.argv[idx + 1]
            if metric in state["metrics"]:
                m = state["metrics"][metric]
                print(f"{metric}: {m['current']:.2f} [{m['trend']}]")
                print(f"  History (last 10): {[round(v,2) for v in m['values'][-10:]]}")
            else:
                print(f"Unknown metric: {metric}")
                print(f"Available: {', '.join(state['metrics'].keys())}")
        return

    # Default: full report
    print("🧘 INTEROCEPTION — Internal State Report")
    print(f"   Sensed at: {state.get('last_sensed', 'never')}")
    print(f"   Sensation #{state.get('sensation_count', 0)}")
    print()
    print(f"   Gut feeling: {state.get('gut_feeling', '')}")
    print()

    m = state["metrics"]
    trend_icon = {"rising": "↑", "falling": "↓", "stable": "→", "slightly_up": "↗", "slightly_down": "↘"}
    for name, data in m.items():
        bar = "█" * int(data["current"] * 20) + "░" * (20 - int(data["current"] * 20))
        trend = trend_icon.get(data["trend"], "?")
        print(f"   {name:20s} [{bar}] {data['current']:.0%} {trend}")

    alerts = state.get("alerts", [])
    if alerts:
        print(f"\n   ⚠️  {len(alerts)} ALERTS:")
        for a in alerts:
            print(f"   {a['level']}: {a['message']}")

if __name__ == "__main__":
    main()
