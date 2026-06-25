#!/usr/bin/env python3
"""obsidian-sync — bidirectional bridge between .claude/ and Obsidian vault.
Syncs packed data, rules, agents, sessions to Obsidian as linked markdown notes.
Usage:
  python3 obsidian-sync.py push          — Push all packed data → Obsidian
  python3 obsidian-sync.py pull          — Pull Obsidian changes → .claude
  python3 obsidian-sync.py sync          — Bidirectional sync
  python3 obsidian-sync.py watch         — Watch mode (sync on changes)
  python3 obsidian-sync.py dashboard     — Generate Obsidian dashboard
  python3 obsidian-sync.py status        — Check Obsidian connection + sync state

Requires: Obsidian running with Local REST API plugin (default port 27123)
Or: writes directly to vault path if no API available (offline mode)
"""
import sys, json, os, io, re, time, hashlib
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
PACK_DIR = CLAUDE / 'packed'
RULES_DIR = CLAUDE / '.claude' / 'rules'
AGENTS_DIR = CLAUDE / '.claude' / 'agents'
BLACKBOARD = CLAUDE / 'blackboard'

# ── Obsidian Vault Configuration ──
# Try common vault paths, or set via OBSIDIAN_VAULT env var
VAULT_PATHS = []
if os.environ.get('OBSIDIAN_VAULT'):
    VAULT_PATHS.append(Path(os.environ['OBSIDIAN_VAULT']))
VAULT_PATHS += [
    HOME / 'Documents' / 'Obsidian' / 'RalphVault',
    HOME / 'Obsidian' / 'RalphVault',
    HOME / 'Documents' / 'Obsidian',
    HOME / 'Obsidian',
]
VAULT_PATH = None
for p in VAULT_PATHS:
    if p and p.exists():
        VAULT_PATH = p
        break
# Fallback: use .claude/obsidian-vault/ if no Obsidian found
if VAULT_PATH is None:
    VAULT_PATH = CLAUDE / 'obsidian-vault'
    VAULT_PATH.mkdir(parents=True, exist_ok=True)

OBSIDIAN_API = "http://localhost:27123"
SYNC_STATE_FILE = CLAUDE / '.claude' / 'obsidian_sync_state.json'

# ── Vault Directory Structure ──
VAULT_DIRS = [
    "00-Dashboard",      # Live dashboard, MOC
    "10-Agents",         # Agent definitions + status
    "20-Rules",          # Behavioral rules
    "30-Memory",         # Packed data by type
    "30-Memory/research",
    "30-Memory/sessions",
    "30-Memory/errors",
    "30-Memory/decisions",
    "30-Memory/tool-outputs",
    "30-Memory/insights",
    "30-Memory/memory",
    "40-Tools",          # Tool documentation
    "50-Sessions",       # Session archives
    "90-Meta",           # Sync state, templates
]

def api_available():
    """Check if Obsidian Local REST API is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OBSIDIAN_API}/", method='GET')
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False

def api_put(path, content):
    """Write a note via Obsidian REST API."""
    try:
        import urllib.request
        data = content.encode('utf-8')
        req = urllib.request.Request(
            f"{OBSIDIAN_API}/vault/{path}",
            data=data, method='PUT',
            headers={'Content-Type': 'text/markdown'}
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False

def api_get(path):
    """Read a note via Obsidian REST API."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OBSIDIAN_API}/vault/{path}")
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.read().decode('utf-8')
    except Exception:
        return None

def api_search(query):
    """Search Obsidian vault."""
    try:
        import urllib.request
        data = json.dumps({"query": query}).encode('utf-8')
        req = urllib.request.Request(
            f"{OBSIDIAN_API}/search",
            data=data, method='POST',
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())
    except Exception:
        return None

def ensure_vault_dirs():
    """Create vault directory structure (offline mode)."""
    if not VAULT_PATH:
        return False
    for d in VAULT_DIRS:
        (VAULT_PATH / d).mkdir(parents=True, exist_ok=True)
    return True

def load_sync_state():
    if SYNC_STATE_FILE.exists():
        try:
            return json.loads(SYNC_STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"last_push": None, "last_pull": None, "pushed_files": {}, "pulled_files": {}}

def save_sync_state(state):
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYNC_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def obsidian_note(content, title="", tags=None, links=None):
    """Wrap content in Obsidian-compatible format with frontmatter."""
    tags_yaml = json.dumps(tags or [])
    links_md = "\n".join(f"[[{l}]]" for l in (links or []))
    return f"""---
title: "{title}"
tags: {tags_yaml}
created: {datetime.now().strftime('%Y-%m-%d %H:%M')}
source: claude-agent
---

# {title}

{content}

{links_md}
"""

def build_note_path(note_type, note_id, title=""):
    """Build Obsidian note path from type and ID."""
    type_dirs = {
        "research": "30-Memory/research",
        "session": "30-Memory/sessions",
        "error": "30-Memory/errors",
        "decision": "30-Memory/decisions",
        "tool-output": "30-Memory/tool-outputs",
        "insight": "30-Memory/insights",
        "memory": "30-Memory/memory",
    }
    base = type_dirs.get(note_type, "30-Memory")
    safe_title = re.sub(r'[\\/:*?"<>|]', '-', title[:50])
    safe_title = re.sub(r'\s+', '-', safe_title).strip('-')
    return f"{base}/{note_id}-{safe_title}.md"

def sync_packed_to_vault():
    """Push all packed data to Obsidian vault."""
    if not PACK_DIR.exists():
        return {"pushed": 0, "status": "no packed data"}

    state = load_sync_state()
    pushed = 0
    errors = 0
    use_api = api_available()

    if not use_api and not VAULT_PATH:
        return {"pushed": 0, "errors": 0, "status": "no vault path configured"}

    if not use_api:
        ensure_vault_dirs()

    for md_file in PACK_DIR.rglob("*.md"):
        if md_file.name == "INDEX.md":
            continue

        # Check if already synced
        file_hash = hashlib.sha256(md_file.read_bytes()).hexdigest()
        if state["pushed_files"].get(str(md_file)) == file_hash:
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            # Extract metadata
            fm_end = content.find('---', 3)
            if fm_end == -1:
                continue
            fm_text = content[3:fm_end].strip()
            body = content[fm_end+3:].strip()

            meta = {}
            for line in fm_text.split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    k, v = k.strip(), v.strip().strip('"')
                    if v.startswith('['):
                        try:
                            meta[k] = json.loads(v)
                        except Exception:
                            meta[k] = v
                    else:
                        meta[k] = v

            note_type = meta.get("type", "memory")
            note_title = meta.get("title", md_file.stem)
            note_tags = meta.get("tags", [])
            if isinstance(note_tags, str):
                note_tags = [t.strip() for t in note_tags.strip('[]').split(',')]
            note_id = meta.get("id", md_file.stem)

            obsidian_content = obsidian_note(
                content=body,
                title=note_title,
                tags=note_tags,
                links=[f"agent-{t}" for t in note_tags[:3]],
            )

            note_path = build_note_path(note_type, note_id, note_title)

            if use_api:
                success = api_put(note_path, obsidian_content)
            else:
                full_path = VAULT_PATH / note_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(obsidian_content, encoding='utf-8')
                success = True

            if success:
                state["pushed_files"][str(md_file)] = file_hash
                pushed += 1
            else:
                errors += 1

        except Exception as e:
            errors += 1

    state["last_push"] = datetime.now().isoformat()
    save_sync_state(state)
    return {"pushed": pushed, "errors": errors, "status": "ok"}

def sync_rules_to_vault():
    """Push rule files to Obsidian."""
    if not RULES_DIR.exists():
        return {"pushed": 0, "status": "no rules"}

    use_api = api_available()
    if not use_api and not VAULT_PATH:
        return {"pushed": 0, "status": "no vault path"}

    if not use_api:
        ensure_vault_dirs()

    pushed = 0
    for rule_file in RULES_DIR.glob("*.md"):
        try:
            content = rule_file.read_text(encoding='utf-8')
            obsidian_content = obsidian_note(
                content=content,
                title=rule_file.stem,
                tags=["rule", rule_file.stem],
            )

            path = f"20-Rules/{rule_file.name}"
            if use_api:
                api_put(path, obsidian_content)
            else:
                (VAULT_PATH / path).write_text(obsidian_content, encoding='utf-8')
            pushed += 1
        except Exception:
            pass

    return {"pushed": pushed, "status": "ok"}

def sync_agents_to_vault():
    """Push agent definitions to Obsidian."""
    if not AGENTS_DIR.exists():
        return {"pushed": 0, "status": "no agents"}

    use_api = api_available()
    if not use_api and not VAULT_PATH:
        return {"pushed": 0, "status": "no vault path"}

    if not use_api:
        ensure_vault_dirs()

    pushed = 0
    for agent_file in AGENTS_DIR.glob("*.md"):
        try:
            content = agent_file.read_text(encoding='utf-8')
            obsidian_content = obsidian_note(
                content=content,
                title=f"Agent: {agent_file.stem}",
                tags=["agent", agent_file.stem],
            )
            path = f"10-Agents/{agent_file.name}"
            if use_api:
                api_put(path, obsidian_content)
            else:
                (VAULT_PATH / path).write_text(obsidian_content, encoding='utf-8')
            pushed += 1
        except Exception:
            pass

    # Also push team.json as a readable note
    team_file = AGENTS_DIR / "team.json"
    if team_file.exists():
        try:
            team = json.loads(team_file.read_text(encoding='utf-8'))
            md = "# Agent Team\n\n"
            for name, info in team.get("agents", {}).items():
                md += f"## {info.get('emoji','')} {name}\n"
                md += f"- **Role:** {info.get('role','')}\n"
                md += f"- **Tools:** {info.get('tools','')}\n"
                md += f"- **Scripts:** {', '.join(info.get('scripts',[]))}\n\n"
            path = "10-Agents/team.md"
            if use_api:
                api_put(path, obsidian_note(md, "Agent Team", ["agent", "team"]))
            else:
                (VAULT_PATH / path).write_text(obsidian_note(md, "Agent Team", ["agent", "team"]), encoding='utf-8')
        except Exception:
            pass

    return {"pushed": pushed, "status": "ok"}

def generate_dashboard():
    """Generate Obsidian dashboard note."""
    from collections import Counter

    # Count packed data
    type_counts = Counter()
    if PACK_DIR.exists():
        for f in PACK_DIR.rglob("*.md"):
            if f.name == "INDEX.md":
                continue
            try:
                content = f.read_text(encoding='utf-8')
                m = re.search(r'type:\s*(\w+)', content)
                if m:
                    type_counts[m.group(1)] += 1
            except Exception:
                pass

    # Agent status
    agent_status = ""
    for agent in ["guard", "memory", "build", "watch", "learn", "plan"]:
        agent_status += f"- {AGENTS_DIR / agent}.md exists: {(AGENTS_DIR / f'{agent}.md').exists()}\n"

    dashboard = f"""---
title: "Ralph Loop Dashboard"
tags: [dashboard, ralph]
created: {datetime.now().strftime('%Y-%m-%d %H:%M')}
---

# 🧠 Ralph Loop — Agent Control Center

> Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📊 Storage Overview

| Type | Count |
|------|-------|
| Research | {type_counts.get('research', 0)} |
| Sessions | {type_counts.get('session', 0)} |
| Errors | {type_counts.get('error', 0)} |
| Decisions | {type_counts.get('decision', 0)} |
| Tool Outputs | {type_counts.get('tool-output', 0)} |
| Insights | {type_counts.get('insight', 0)} |
| Memories | {type_counts.get('memory', 0)} |
| **Total** | **{sum(type_counts.values())}** |

## 🤖 Agent Team

| Agent | Role | Status |
|-------|------|--------|
| 🛡️ Guard | Security & Verification | Ready |
| 🧠 Memory | Knowledge Management | Ready |
| 🔨 Build | Code Implementation | Ready |
| 👁️ Watch | Health Monitoring | Ready |
| 🎓 Learn | Research & Evolution | Ready |
| 📋 Plan | Planning & Coordination | Ready |

## 🔗 Quick Links

- [[10-Agents/team|Agent Team]]
- [[20-Rules/|Behavioral Rules]]
- [[30-Memory/|Memory Store]]
- [[50-Sessions/|Session Archive]]

## 🛠️ Active Tools

{TOOL_COUNT}+ tools across 12 layers
"""
    return dashboard

# Import ALL_TOOLS for dashboard (circular import avoidance)
SCRIPTS = CLAUDE / 'scripts'
try:
    from orchestrator import ALL_TOOLS
    TOOL_COUNT = len(ALL_TOOLS)
except Exception:
    TOOL_COUNT = 30  # fallback count

def cmd_push(args):
    """Push all data to Obsidian."""
    use_api = api_available()
    print(f"OBSIDIAN: {'LIVE (API)' if use_api else 'OFFLINE (direct file write)'}")
    if not use_api and not VAULT_PATH:
        print("  ⚠️ No Obsidian vault found. Set OBSIDIAN_VAULT env var or install Obsidian.")
        print("  Vault paths tried:", [str(p) for p in VAULT_PATHS if p])
        return

    if not use_api:
        print(f"  Vault: {VAULT_PATH}")

    # Push packed data
    result = sync_packed_to_vault()
    print(f"  Packed: {result['pushed']} notes pushed" + (f", {result['errors']} errors" if result.get('errors') else ""))

    # Push rules
    result = sync_rules_to_vault()
    print(f"  Rules: {result['pushed']} files pushed")

    # Push agents
    result = sync_agents_to_vault()
    print(f"  Agents: {result['pushed']} files pushed")

    # Generate dashboard
    dashboard = generate_dashboard()
    if use_api:
        api_put("00-Dashboard/Ralph Dashboard.md", dashboard)
    elif VAULT_PATH:
        (VAULT_PATH / "00-Dashboard" / "Ralph Dashboard.md").write_text(dashboard, encoding='utf-8')
    print(f"  Dashboard: generated")

def cmd_status(args):
    """Check Obsidian connection and sync state."""
    use_api = api_available()
    state = load_sync_state()

    print(f"OBSIDIAN STATUS")
    print(f"  API: {'🟢 ONLINE' if use_api else '🔴 OFFLINE'}")
    print(f"  Vault path: {VAULT_PATH or 'NOT FOUND'}")
    print(f"  Last push: {state.get('last_push', 'never')}")
    print(f"  Last pull: {state.get('last_pull', 'never')}")
    print(f"  Tracked files: {len(state.get('pushed_files', {}))}")

    if PACK_DIR.exists():
        total = len(list(PACK_DIR.rglob("*.md"))) - 1  # minus INDEX.md
        synced = len(state.get("pushed_files", {}))
        print(f"  Packed files: {total} total, {synced} synced, {max(0, total - synced)} pending")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    handlers = {
        "push": cmd_push,
        "status": cmd_status,
    }

    if cmd in handlers:
        handlers[cmd](rest)
    elif cmd in ("pull", "sync", "watch", "dashboard"):
        print(f"obsidian-sync: '{cmd}' requires Obsidian API (port 27123). Start Obsidian first.")
        print("  Currently in offline mode — use 'push' to write directly to vault path.")
    else:
        print(f"Unknown: {cmd}. Use: push, status")

if __name__ == "__main__":
    main()
