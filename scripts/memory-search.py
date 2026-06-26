#!/usr/bin/env python3
"""memory-search — unified search across file-based memories with relevance ranking.
Usage:
  python3 memory-search.py "encoding bug"              # Keyword search
  python3 memory-search.py --type error                 # By type
  python3 memory-search.py --domain security            # By domain
  python3 memory-search.py --stale                      # Find aging/expired
  python3 memory-search.py --recent 5                   # Most recent N
  python3 memory-search.py --since 7d                   # Last 7 days
  python3 memory-search.py --inject                     # Context injection (~250 tokens)
  python3 memory-search.py --inject --project "my-app"  # Project-scoped injection
  python3 memory-search.py --stats                      # Memory system stats

Output modes:
  default  : human-readable list with scores
  --json   : machine-readable JSON
  --inject : compact context block for LLM prompt injection
"""
import sys, json, os, io
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
MEMORY_DIR = HOME / '.claude' / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'
MEMORY_INDEX = MEMORY_DIR / 'MEMORY.md'
STATE_FILE = HOME / '.claude' / '.claude' / 'memory_scores.json'

def parse_memory_file(filepath):
    """Parse a memory file and extract frontmatter + body."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return None

    if not content.startswith('---'):
        return None

    end = content.find('---', 3)
    if end == -1:
        return None

    fm_text = content[3:end].strip()
    body = content[end+3:].strip()

    meta = {}
    for line in fm_text.split('\n'):
        line = line.strip()
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip().strip('"')

    # Normalize known fields
    for int_field in ['access_count']:
        if int_field in meta:
            try: meta[int_field] = int(meta[int_field])
            except: pass

    meta["_file"] = str(filepath.relative_to(MEMORY_DIR))
    meta["_body"] = body[:800]
    meta["_size"] = len(content)
    meta["_full_body"] = body

    return meta

def load_all_memories():
    """Load all memory files with parsed metadata."""
    if not MEMORY_DIR.exists():
        return []

    memories = []
    for md_file in MEMORY_DIR.rglob("*.md"):
        if md_file.name == "MEMORY.md":
            continue
        mem = parse_memory_file(md_file)
        if mem and 'atomic_id' in mem:
            memories.append(mem)

    return memories

def load_scoring_state():
    """Load Ebbinghaus scoring state."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def score_memory(mem, state):
    """Calculate Ebbinghaus score for a memory."""
    aid = mem.get('atomic_id', '')
    created_str = mem.get('created', '')
    now = datetime.now()

    try:
        created_dt = datetime.fromisoformat(created_str)
    except Exception:
        created_dt = now

    days_since_creation = max(0, (now - created_dt).days)

    es = state.get(aid, {})
    access_count = es.get('access_count', 0) if isinstance(es, dict) else 0
    last_access_str = es.get('last_access') if isinstance(es, dict) else None
    applied = es.get('applied_successfully', False) if isinstance(es, dict) else False

    days_since_access = days_since_creation
    if last_access_str:
        try:
            days_since_access = max(0, (now - datetime.fromisoformat(last_access_str)).days)
        except Exception:
            pass

    score = min(1.0,
        pow(2.71828, -days_since_creation / 30) +
        min(access_count * 0.05, 0.3) +
        (0.15 if days_since_access < 7 else 0.10 if days_since_access < 30 else 0) +
        (0.20 if applied else 0)
    )
    if days_since_access >= 60:
        score *= 0.5

    return round(score, 2)

def score_tag(score):
    if score >= 0.8: return "fresh"
    if score >= 0.5: return "aging"
    if score >= 0.3: return "stale"
    return "expired"

def search(memories, query=None, ptype=None, domain=None, hierarchy=None,
           since=None, stale_only=False, recent=None, project=None):
    """Search and rank memories."""
    results = []

    for mem in memories:
        # Type filter
        if ptype and mem.get('type') != ptype:
            continue

        # Domain filter
        if domain and mem.get('domain') != domain:
            continue

        # Hierarchy filter
        if hierarchy and mem.get('hierarchy') != hierarchy:
            continue

        # Project scope filter
        if project:
            scope = mem.get('scope', 'global')
            if scope != 'global' and project not in scope:
                continue

        # Date filter
        if since:
            created = mem.get('created', '')
            if created:
                try:
                    if datetime.fromisoformat(created) < since:
                        continue
                except Exception:
                    pass

        # Stale filter
        if stale_only:
            created = mem.get('created', '')
            if created:
                try:
                    days = (datetime.now() - datetime.fromisoformat(created)).days
                    if days < 30:
                        continue
                except Exception:
                    continue

        # Text search with relevance scoring
        relevance = 0.0
        if query:
            q = query.lower()
            title = mem.get('description', '').lower()
            body = mem.get('_body', '').lower()
            tags = str(mem.get('type', '')).lower()

            # Title match (highest weight)
            if q in title:
                relevance += 3.0
            # Description match
            elif any(w in title for w in q.split()):
                relevance += 1.5
            # Body match
            if q in body:
                relevance += 1.0
            elif any(w in body for w in q.split()):
                relevance += 0.5
            # Tag match
            if q in tags:
                relevance += 0.5

            if relevance == 0:
                continue
        else:
            relevance = 1.0

        results.append((mem, relevance))

    # Sort by relevance desc, then by created date desc
    results.sort(key=lambda x: (x[1], x[0].get('created', '')), reverse=True)

    if recent and len(results) > recent:
        results = results[:recent]

    return [r[0] for r in results]

def inject_context(memories, state, max_tokens=300, project=None):
    """Generate compact context block for LLM injection."""
    if not memories:
        return ""

    # Filter by project scope
    if project:
        memories = [m for m in memories if m.get('scope', 'global') in ('global', f'project:{project}')]

    # Score and sort: freshest + most relevant first
    scored = [(score_memory(m, state), m) for m in memories]
    scored.sort(key=lambda x: (-x[0], x[1].get('created', '')))

    lines = ["## Relevant Memories (auto-injected)"]
    token_est = 20

    type_icons = {
        "preference": "⚙️", "feedback": "📝", "project": "📂", "reference": "📚",
        "error": "🔴", "insight": "💎", "decision": "✅"
    }

    for score, mem in scored[:8]:
        icon = type_icons.get(mem.get('type', ''), '📄')
        desc = mem.get('description', 'No description')[:100]
        tag = score_tag(score)
        body_preview = mem.get('_body', '')[:150].replace('\n', ' ')

        line = f"- {icon} [{tag}] {desc}"
        line_tokens = len(line) // 3
        if token_est + line_tokens > max_tokens:
            break
        lines.append(line)
        token_est += line_tokens

        # Add body snippet for top 3
        if len(lines) <= 4 and body_preview:
            snippet = f"  ↳ {body_preview}"
            snip_tokens = len(snippet) // 3
            if token_est + snip_tokens <= max_tokens:
                lines.append(snippet)
                token_est += snip_tokens

    return '\n'.join(lines)

def get_stats(memories, state):
    """Generate memory system statistics."""
    by_type = {}
    by_hierarchy = {}
    by_score = {"fresh": 0, "aging": 0, "stale": 0, "expired": 0}

    for mem in memories:
        t = mem.get('type', 'unknown')
        h = mem.get('hierarchy', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
        by_hierarchy[h] = by_hierarchy.get(h, 0) + 1

        score = score_memory(mem, state)
        by_score[score_tag(score)] += 1

    return {
        "total": len(memories),
        "by_type": by_type,
        "by_hierarchy": by_hierarchy,
        "by_freshness": by_score,
        "index_entries": MEMORY_INDEX.read_text(encoding='utf-8').count('- [') if MEMORY_INDEX.exists() else 0,
    }

def main():
    use_json = "--json" in sys.argv
    do_inject = "--inject" in sys.argv
    stale_only = "--stale" in sys.argv
    do_stats = "--stats" in sys.argv

    query = None; ptype = None; domain = None; hierarchy = None
    since = None; recent = None; project = None

    for i, arg in enumerate(sys.argv):
        if arg == "--type" and i + 1 < len(sys.argv):
            ptype = sys.argv[i + 1]
        elif arg == "--domain" and i + 1 < len(sys.argv):
            domain = sys.argv[i + 1]
        elif arg == "--hierarchy" and i + 1 < len(sys.argv):
            hierarchy = sys.argv[i + 1]
        elif arg == "--since" and i + 1 < len(sys.argv):
            val = sys.argv[i + 1]
            if val.endswith('d'):
                since = datetime.now() - timedelta(days=int(val[:-1]))
            elif val.endswith('h'):
                since = datetime.now() - timedelta(hours=int(val[:-1]))
        elif arg == "--recent" and i + 1 < len(sys.argv):
            recent = int(sys.argv[i + 1])
        elif arg == "--project" and i + 1 < len(sys.argv):
            project = sys.argv[i + 1]
        elif i == 1 and not arg.startswith('--'):
            query = arg

    memories = load_all_memories()
    state = load_scoring_state()

    if do_stats:
        stats = get_stats(memories, state)
        if use_json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print(f"MEMORY STATS: {stats['total']} total")
            print(f"  By type:    {json.dumps(stats['by_type'])}")
            print(f"  By level:   {json.dumps(stats['by_hierarchy'])}")
            print(f"  Freshness:  {json.dumps(stats['by_freshness'])}")
        return

    results = search(memories, query=query, ptype=ptype, domain=domain,
                     hierarchy=hierarchy, since=since, stale_only=stale_only,
                     recent=recent, project=project)

    if do_inject:
        print(inject_context(results if results else memories, state, project=project))
        return

    # Score results
    scored = [(score_memory(m, state), m) for m in results]
    scored.sort(key=lambda x: -x[0])

    if use_json:
        output = []
        for score, mem in scored:
            output.append({
                "id": mem.get("atomic_id"),
                "type": mem.get("type"),
                "hierarchy": mem.get("hierarchy"),
                "description": mem.get("description"),
                "created": mem.get("created"),
                "score": score,
                "tag": score_tag(score),
                "file": mem.get("_file"),
                "preview": mem.get("_body", "")[:200],
            })
        print(json.dumps({"total": len(results), "results": output}, ensure_ascii=False, indent=2))
    else:
        type_icons = {
            "preference": "⚙️", "feedback": "📝", "project": "📂", "reference": "📚",
            "error": "🔴", "insight": "💎", "decision": "✅"
        }
        print(f"MEMORY: {len(results)} results")
        for score, mem in scored:
            icon = type_icons.get(mem.get('type', ''), '📄')
            aid = mem.get('atomic_id', '?')
            desc = mem.get('description', 'No description')[:100]
            created = (mem.get('created', '') or '')[:10]
            tag = score_tag(score)
            print(f"  {icon} [{tag}] ({score:.2f}) [{created}] {aid}")
            print(f"     {desc}")
            # Show body preview for detailed view
            body = mem.get('_body', '')[:120].replace('\n', ' ')
            if body:
                print(f"     ↳ {body}")

if __name__ == "__main__":
    main()
