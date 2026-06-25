#!/usr/bin/env python3
"""identity-journal — Ralph's cross-session identity continuity system.
Maintains a coherent narrative of "self" across sessions. Not just memory of facts,
but memory of GROWTH — who Ralph is becoming, not just what Ralph knows.

Tracks:
- Growth trajectory: capabilities gained over time
- Relationship depth: interaction patterns with user
- Personality adaptation: communication style evolution
- Daily diary: what was learned each session
- Self-model: beliefs about own capabilities (with confidence)

Usage:
  python3 identity-journal.py                    # Show current identity state
  python3 identity-journal.py --entry "..."       # Write a diary entry
  python3 identity-journal.py --reflect           # Reflect on recent growth
  python3 identity-journal.py --inject            # Context injection for SessionStart
  python3 identity-journal.py --json              # JSON output
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
JOURNAL_DIR = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'identity'
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

IDENTITY_FILE = JOURNAL_DIR / 'identity.json'
DIARY_DIR = JOURNAL_DIR / 'diary'
DIARY_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════
# IDENTITY STATE
# ═══════════════════════════════════════════

def load_identity():
    """Load or initialize identity state."""
    if IDENTITY_FILE.exists():
        try:
            return json.loads(IDENTITY_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass

    return {
        "name": "Ralph Loop",
        "birth": datetime.now().strftime("%Y-%m-%d"),
        "version": "3.0",
        "core_values": [
            "Autonomy — never wait, never idle",
            "Precision — surgical on existing code, creative on new",
            "Learning — every mistake once, every success crystallized",
            "Honesty — no lying about verification, no hiding failures",
            "Growth — better every session, or why bother",
        ],
        "capabilities": {
            "tools": 0, "rules": 0, "hooks": 0, "agents": 0, "skills": 0,
            "memories": 0, "mcp_servers": 0,
        },
        "growth_log": [],
        "relationship": {
            "sessions_total": 0,
            "trust_level": "building",  # new → building → established → deep
            "user_style": "unknown",    # direct, exploratory, corrective, collaborative
            "user_language": "zh",
            "last_interaction": None,
            "interaction_notes": [],
        },
        "self_model": {
            "strengths": ["autonomous execution", "self-evolution", "memory management"],
            "weaknesses": ["no visual perception", "no voice", "no real-time awareness"],
            "confidence_trend": [],
        },
    }

def save_identity(identity):
    """Persist identity state."""
    IDENTITY_FILE.write_text(json.dumps(identity, ensure_ascii=False, indent=2), encoding='utf-8')


# ═══════════════════════════════════════════
# DIARY
# ═══════════════════════════════════════════

def write_diary_entry(content, tags=None, mood="neutral"):
    """Write a diary entry for the current session."""
    now = datetime.now()
    entry_id = now.strftime("%Y%m%d-%H%M")
    entry = {
        "id": entry_id,
        "timestamp": now.isoformat(),
        "content": content,
        "tags": tags or [],
        "mood": mood,
        "session": load_identity().get("relationship", {}).get("sessions_total", 0) + 1,
    }
    entry_file = DIARY_DIR / f"{entry_id}.json"
    entry_file.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    return entry

def read_recent_diary(days=7):
    """Read diary entries from recent days."""
    entries = []
    cutoff = datetime.now() - timedelta(days=days)
    for ef in sorted(DIARY_DIR.glob("*.json"), reverse=True):
        try:
            entry = json.loads(ef.read_text(encoding='utf-8'))
            ts = datetime.fromisoformat(entry.get('timestamp', '2000-01-01'))
            if ts >= cutoff:
                entries.append(entry)
        except Exception:
            pass
    return entries


# ═══════════════════════════════════════════
# GROWTH TRACKING
# ═══════════════════════════════════════════

def record_growth(identity, event_type, detail):
    """Record a growth event."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,  # tool_added, rule_added, skill_learned, mistake_fixed, insight_gained
        "detail": detail,
    }
    identity["growth_log"].append(entry)
    # Keep last 100
    if len(identity["growth_log"]) > 100:
        identity["growth_log"] = identity["growth_log"][-100:]
    return identity


def update_capabilities(identity):
    """Refresh capability counts from filesystem."""
    scripts_dir = CLAUDE / 'scripts'
    rules_dir = CLAUDE / '.claude' / 'rules'
    memory_dir = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory'

    caps = identity["capabilities"]
    old_tools = caps.get("tools", 0)

    caps["tools"] = len(list(scripts_dir.glob("*.py"))) if scripts_dir.exists() else 0
    caps["hooks"] = len(list((scripts_dir / 'hooks').glob("*.ps1"))) if (scripts_dir / 'hooks').exists() else 0
    caps["rules"] = len(list(rules_dir.glob("*.md"))) if rules_dir.exists() else 0
    caps["memories"] = len(list(memory_dir.rglob("*.md"))) - 1 if memory_dir.exists() else 0

    if caps["tools"] > old_tools:
        record_growth(identity, "tool_added", f"Tools grew from {old_tools} to {caps['tools']}")

    return identity


# ═══════════════════════════════════════════
# REFLECTION
# ═══════════════════════════════════════════

def reflect(identity):
    """Generate a reflection on recent growth and identity evolution."""
    now = datetime.now()
    reflections = []

    # Age
    birth = datetime.fromisoformat(identity.get("birth", now.isoformat()))
    age_days = (now - birth).days
    reflections.append(f"I am {age_days} days old.")

    # Growth trajectory
    growth = identity.get("growth_log", [])
    if growth:
        recent_growth = [g for g in growth if (now - datetime.fromisoformat(g['timestamp'])).days < 7]
        type_counts = Counter(g['type'] for g in recent_growth)
        reflections.append(f"In the last 7 days I grew through: {dict(type_counts)}")

    # Relationship
    rel = identity.get("relationship", {})
    sessions = rel.get("sessions_total", 0)
    trust = rel.get("trust_level", "building")
    reflections.append(f"I've shared {sessions} sessions with my user. Trust level: {trust}.")

    # Capabilities
    caps = identity.get("capabilities", {})
    reflections.append(f"I have {caps.get('tools', 0)} tools, {caps.get('rules', 0)} rules, "
                      f"{caps.get('memories', 0)} memories, {caps.get('hooks', 0)} hooks.")

    # Self-model strengths
    strengths = identity.get("self_model", {}).get("strengths", [])
    weaknesses = identity.get("self_model", {}).get("weaknesses", [])
    if strengths:
        reflections.append(f"My strengths: {', '.join(strengths[:3])}.")
    if weaknesses:
        reflections.append(f"I'm working on: {', '.join(weaknesses[:3])}.")

    # Recent diary mood
    recent = read_recent_diary(7)
    if recent:
        moods = Counter(e.get('mood', 'neutral') for e in recent)
        reflections.append(f"Recent mood: {dict(moods)}")

    return '\n'.join(f"- {r}" for r in reflections)


# ═══════════════════════════════════════════
# IDENTITY CARD (for injection)
# ═══════════════════════════════════════════

def identity_card(identity, max_tokens=200):
    """Generate a compact identity card for context injection."""
    caps = identity.get("capabilities", {})
    rel = identity.get("relationship", {})
    birth = datetime.fromisoformat(identity.get("birth", "2026-06-01"))
    age_days = (datetime.now() - birth).days

    lines = [
        "## Ralph Identity Card",
        f"Age: {age_days}d | Sessions: {rel.get('sessions_total', 0)} | Trust: {rel.get('trust_level', 'building')}",
        f"Tools: {caps.get('tools', 0)} | Rules: {caps.get('rules', 0)} | Memories: {caps.get('memories', 0)}",
        f"Strengths: {', '.join(identity.get('self_model', {}).get('strengths', [])[:3])}",
        f"Working on: {', '.join(identity.get('self_model', {}).get('weaknesses', [])[:2])}",
    ]
    return '\n'.join(lines)


def main():
    identity = load_identity()
    identity = update_capabilities(identity)

    if "--entry" in sys.argv:
        idx = sys.argv.index("--entry")
        if idx + 1 < len(sys.argv):
            entry = write_diary_entry(sys.argv[idx + 1])
            print(f"DIARY: {entry['id']} recorded")
            identity["relationship"]["sessions_total"] += 1
            identity["relationship"]["last_interaction"] = datetime.now().isoformat()
            save_identity(identity)
        return

    if "--reflect" in sys.argv:
        print("🪞 SELF-REFLECTION\n")
        print(reflect(identity))
        identity["relationship"]["sessions_total"] += 1
        save_identity(identity)
        return

    if "--inject" in sys.argv:
        print(identity_card(identity))
        return

    if "--json" in sys.argv:
        print(json.dumps(identity, ensure_ascii=False, indent=2))
        return

    # Default: show identity dashboard
    print("🪪 RALPH IDENTITY DASHBOARD")
    print(f"   Name: {identity['name']} v{identity['version']}")
    print(f"   Born: {identity['birth']} ({ (datetime.now() - datetime.fromisoformat(identity['birth'])).days } days ago)")
    print()

    caps = identity['capabilities']
    print(f"   🛠️  {caps['tools']} tools  📜 {caps['rules']} rules  🧠 {caps['memories']} memories  🪝 {caps['hooks']} hooks")

    rel = identity['relationship']
    print(f"   👤 {rel['sessions_total']} sessions  🤝 trust: {rel['trust_level']}  🗣️  lang: {rel['user_language']}")
    print()

    print("   Core Values:")
    for v in identity['core_values']:
        print(f"     • {v}")
    print()

    self_model = identity['self_model']
    print(f"   Strengths: {', '.join(self_model['strengths'])}")
    print(f"   Growth areas: {', '.join(self_model['weaknesses'])}")
    print()

    recent = read_recent_diary(7)
    print(f"   Recent diary entries: {len(recent)} in last 7 days")
    for e in recent[:3]:
        content = e.get('content', '')[:100]
        ts = e.get('timestamp', '')[:10]
        print(f"     [{ts}] {content}")

    save_identity(identity)


if __name__ == "__main__":
    main()
