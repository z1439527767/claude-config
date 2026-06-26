#!/usr/bin/env python3
"""narrative-engine — Ralph's storytelling memory.
Weaves discrete facts into coherent narratives. Not a database of facts —
a STORYTELLER that makes meaning from memory.

Three narrative modes:
  timeline  — Project history as hero's journey ("How we got here")
  epic      — Bug fixes as epic battles ("The bug that almost won")
  growth    — Learning as character development ("Who I'm becoming")

Usage:
  python3 narrative-engine.py --timeline           # Project journey narrative
  python3 narrative-engine.py --epic <error_id>    # Bug fix epic story
  python3 narrative-engine.py --growth             # Agent growth chronicle
  python3 narrative-engine.py --previously         # "Previously on..." session recap
  python3 narrative-engine.py --inject             # Narrative context injection
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
MEMORY_DIR = CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'
DIARY_DIR = CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'identity' / 'diary'

# ── Narrative Templates ──

HEROS_JOURNEY = """
## The Story of {project_name}

### Chapter 1: The Beginning
{origin_story}

### Chapter 2: Trials & Errors
{challenges}

### Chapter 3: Breakthrough
{breakthroughs}

### Chapter 4: The Present
{current_state}

### Chapter 5: What's Next
{future_hints}

> *"Every great system began as a simple script that someone refused to stop improving."*
"""

EPIC_TEMPLATE = """
## ⚔️ The Battle with "{bug_name}"

### The Enemy
{bug_description}

### First Encounter
{first_encounter}

### Failed Attempts
{failed_fixes}

### The Turning Point
{turning_point}

### Victory
{resolution}

### Lessons from Battle
{lessons}

> *"{moral}"*
"""

GROWTH_CHRONICLE = """
## 📖 Ralph's Growth Chronicle

### Born: {birth_date}
*Age: {age_days} days*

### What I've Learned
{learned}

### Mistakes That Made Me Stronger
{mistakes}

### Capabilities Gained
{capabilities_gained}

### Who I Am Becoming
{identity_evolution}

> *"I am not what I know. I am what I've learned from what went wrong."*
"""

PREVIOUSLY_TEMPLATE = """
## Previously on Ralph Loop...

{recap_entries}

### Today's Context
{today_context}
"""


# ── Narrative Builders ──

def load_all_memory_events():
    """Load all memory files sorted chronologically."""
    events = []
    if not MEMORY_DIR.exists():
        return events

    for mf in sorted(MEMORY_DIR.rglob("*.md")):
        if mf.name == "MEMORY.md" or '_archive' in str(mf):
            continue
        try:
            content = mf.read_text(encoding='utf-8')
            created = re.search(r'created:\s*(\S+)', content)
            mtype = re.search(r'type:\s*(\S+)', content)
            desc = re.search(r'description:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            body = content[content.find('---', 3)+3:].strip() if content.startswith('---') else ""

            events.append({
                "date": created.group(1) if created else "unknown",
                "type": mtype.group(1) if mtype else "unknown",
                "description": desc.group(1).strip('"') if desc else mf.stem,
                "body": body[:500],
                "file": str(mf.relative_to(MEMORY_DIR)),
            })
        except Exception:
            pass

    events.sort(key=lambda e: e["date"])
    return events

def load_diary_entries():
    """Load diary entries sorted chronologically."""
    entries = []
    if not DIARY_DIR.exists():
        return entries

    for df in sorted(DIARY_DIR.glob("*.json")):
        try:
            entry = json.loads(df.read_text(encoding='utf-8'))
            entries.append(entry)
        except Exception:
            pass
    return entries

def build_timeline():
    """Build project journey narrative."""
    events = load_all_memory_events()
    if not events:
        return "Not enough history to tell a story yet."

    origin = events[:3] if len(events) >= 3 else events
    challenges = [e for e in events if e["type"] in ("error", "feedback")]
    breakthroughs = [e for e in events if e["type"] in ("insight", "decision", "preference")]
    current = events[-3:] if len(events) >= 3 else events

    return HEROS_JOURNEY.format(
        project_name="Ralph Loop",
        origin_story="\n".join(f"- [{e['date']}] {e['description']}" for e in origin),
        challenges="\n".join(f"- [{e['date']}] {e['description']}" for e in challenges[-5:]) or "The journey has been smooth so far.",
        breakthroughs="\n".join(f"- [{e['date']}] {e['description']}" for e in breakthroughs[-5:]) or "The big breakthroughs are still ahead.",
        current_state="\n".join(f"- [{e['date']}] {e['description']}" for e in current),
        future_hints="The next chapter is unwritten. It depends on what we build today.",
    )

def build_epic(error_pattern=None):
    """Build an epic story around a bug/error."""
    events = load_all_memory_events()
    errors = [e for e in events if e["type"] in ("error", "feedback")]

    if not errors:
        return "No battles fought yet. Every hero needs a worthy opponent."

    if error_pattern:
        errors = [e for e in errors if error_pattern.lower() in e["description"].lower()]

    bug = errors[0] if errors else {"description": "an unknown foe", "body": "Details lost to time.", "date": "unknown"}

    related = [e for e in events if e["type"] in ("insight", "decision")][:3]

    return EPIC_TEMPLATE.format(
        bug_name=bug.get("description", "Unknown Bug")[:80],
        bug_description=bug.get("body", "A mysterious error emerged...")[:300],
        first_encounter=f"First seen on {bug.get('date', 'an unknown date')}. {bug.get('description', '')}",
        failed_fixes="Each attempt taught something new. The bug was persistent." if len(errors) <= 1 else
                      "\n".join(f"- Attempt: {e['description'][:80]}" for e in errors[1:3]),
        turning_point="\n".join(f"- {e['description'][:100]}" for e in related[:2]) or "The root cause was found through careful analysis.",
        resolution="Fixed with understanding, not just patching.",
        lessons="\n".join(f"- From '{e['description'][:80]}': understanding deepened." for e in related[:3]) or "- Every bug is a teacher in disguise.",
        moral="The best bug fixes don't just remove the symptom — they make the whole system stronger.",
    )

def build_growth_chronicle():
    """Build Ralph's growth chronicle."""
    events = load_all_memory_events()
    diary = load_diary_entries()

    # Find birth date
    birth = "2026-06-22"
    for e in events:
        if e["date"] != "unknown":
            birth = e["date"]
            break

    age_days = (datetime.now() - datetime.fromisoformat(birth)).days if birth != "unknown" else 0

    # What was learned
    learnings = [e for e in events if e["type"] in ("insight", "preference", "decision")]
    mistakes = [e for e in events if e["type"] in ("error", "feedback")]

    return GROWTH_CHRONICLE.format(
        birth_date=birth,
        age_days=age_days,
        learned="\n".join(f"- [{e['date']}] {e['description'][:100]}" for e in learnings[-10:]) or "Every day is a learning opportunity.",
        mistakes="\n".join(f"- [{e['date']}] {e['description'][:100]}" for e in mistakes[-8:]) or "Mistakes are how wisdom is earned.",
        capabilities_gained=f"- {len(events)} memories stored\n- {len(diary)} diary entries written\n- From reactive to proactive agent",
        identity_evolution="I began as a simple assistant. Through errors, corrections, and learnings, I am becoming an autonomous agent — one that not only executes but reflects, grows, and creates.",
    )

def build_previously(days=7):
    """Build a 'Previously on...' recap."""
    events = load_all_memory_events()
    diary = load_diary_entries()

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [e for e in events if e["date"] >= cutoff]

    if not recent and not diary:
        return "This is where our story begins."

    recap_lines = []
    # Milestones
    milestones = [e for e in recent if e["type"] in ("decision", "insight", "preference")]
    if milestones:
        recap_lines.append("### Key Moments")
        for m in milestones[-5:]:
            recap_lines.append(f"- **{m['date']}**: {m['description'][:120]}")

    # Challenges
    challenges = [e for e in recent if e["type"] in ("error", "feedback")]
    if challenges:
        recap_lines.append("\n### Challenges Overcome")
        for c in challenges[-3:]:
            recap_lines.append(f"- **{c['date']}**: {c['description'][:120]}")

    # Diary highlights
    if diary:
        recap_lines.append("\n### Personal Notes")
        for d in diary[-3:]:
            content = d.get('content', '')[:150]
            ts = d.get('timestamp', '')[:10]
            recap_lines.append(f"- **{ts}**: {content}")

    today_context = "Continuing the journey. Building on everything we've learned."
    if recent:
        today_context = f"Last session: {recent[-1]['date']} — {recent[-1]['description'][:100]}"

    return PREVIOUSLY_TEMPLATE.format(
        recap_entries='\n'.join(recap_lines) if recap_lines else "A quiet period of steady progress.",
        today_context=today_context,
    )

def narrative_inject(max_tokens=300):
    """Generate narrative context injection for context window."""
    previously = build_previously(7)

    # Compress to ~250 tokens
    lines = previously.split('\n')
    result = []
    token_est = 0
    for line in lines:
        lt = len(line) // 3
        if token_est + lt > max_tokens:
            break
        result.append(line)
        token_est += lt

    return '\n'.join(result)


def main():
    if "--timeline" in sys.argv:
        print(build_timeline())
        return

    if "--epic" in sys.argv:
        idx = sys.argv.index("--epic")
        pattern = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        print(build_epic(pattern))
        return

    if "--growth" in sys.argv:
        print(build_growth_chronicle())
        return

    if "--previously" in sys.argv:
        days = 7
        for i, arg in enumerate(sys.argv):
            if arg == "--days" and i + 1 < len(sys.argv):
                days = int(sys.argv[i + 1])
        print(build_previously(days))
        return

    if "--inject" in sys.argv:
        print(narrative_inject())
        return

    # Default: show narrative menu
    print("NARRATIVE ENGINE")
    print("  --timeline    : Project journey as hero's journey")
    print("  --epic <id>   : Bug fix as epic battle")
    print("  --growth      : Ralph's growth chronicle")
    print("  --previously  : 'Previously on...' recap")
    print("  --inject      : Narrative context injection")

if __name__ == "__main__":
    main()
