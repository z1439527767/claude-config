#!/usr/bin/env python3
"""packed-retrieve — search and load packed data for context injection.
Usage:
  python3 packed-retrieve.py --type error --recent 5     # Last 5 errors
  python3 packed-retrieve.py --tag security               # All security-tagged
  python3 packed-retrieve.py --since 7d                   # Last 7 days
  python3 packed-retrieve.py --search "encoding bug"      # Full-text search
  python3 packed-retrieve.py --inject                     # Print ~200 token context inject
  python3 packed-retrieve.py --index                      # Print full index

Output: structured list of matching packed files with summaries.
--inject mode: returns compact context suitable for prepending to LLM call.
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
PACK_DIR = HOME / '.claude' / 'packed'

def parse_packed(filepath):
    """Parse a packed file and return its metadata + content."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return None

    if not content.startswith('---'):
        return None

    # Extract frontmatter
    end = content.find('---', 3)
    if end == -1:
        return None

    fm_text = content[3:end].strip()
    body = content[end+3:].strip()

    meta = {}
    for line in fm_text.split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            k, v = k.strip(), v.strip()
            # Parse JSON arrays
            if v.startswith('[') and v.endswith(']'):
                try:
                    meta[k] = json.loads(v)
                except Exception:
                    meta[k] = v
            else:
                meta[k] = v.strip('"')

    meta["_file"] = str(filepath)
    meta["_body"] = body[:500]  # First 500 chars for preview
    meta["_size"] = len(content)
    return meta

def load_all():
    """Load all packed files."""
    if not PACK_DIR.exists():
        return []
    all_entries = []
    for f in PACK_DIR.rglob('*.md'):
        entry = parse_packed(f)
        if entry and 'id' in entry:
            all_entries.append(entry)
    # Sort by created date (newest first)
    all_entries.sort(key=lambda e: e.get('created', ''), reverse=True)
    return all_entries

def filter_entries(entries, ptype=None, tag=None, since=None, search=None, recent=None):
    """Filter entries by criteria."""
    results = []

    for e in entries:
        # Type filter
        if ptype and e.get('type') != ptype:
            continue

        # Tag filter
        if tag:
            tags = e.get('tags', [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.strip('[]').split(',')]
            if tag not in tags:
                continue

        # Since filter
        if since:
            created = e.get('created', '')
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    if dt < since:
                        continue
                except Exception:
                    pass

        # Full-text search
        if search:
            body = e.get('_body', '')
            title = str(e.get('title', ''))
            tags = str(e.get('tags', ''))
            searchable = f"{title} {tags} {body}".lower()
            if search.lower() not in searchable:
                continue

        results.append(e)

    # Limit
    if recent and len(results) > recent:
        results = results[:recent]

    return results

def inject_context(entries, max_tokens=300):
    """Generate compact context injection from entries."""
    if not entries:
        return ""

    lines = ["## Recent Context (packed data)"]
    token_est = 20  # Overhead

    for e in entries[:10]:
        etype = e.get('type', '?')
        title = e.get('title', 'No title')[:80]
        tags = e.get('tags', [])
        if isinstance(tags, list):
            tag_str = ', '.join(tags[:3])
        else:
            tag_str = str(tags)

        line = f"- [{etype}] {title} ({tag_str})"
        line_tokens = len(line) // 3
        if token_est + line_tokens > max_tokens:
            break
        lines.append(line)
        token_est += line_tokens

    return '\n'.join(lines)

def build_index(entries):
    """Build a quick-scan index of all packed data."""
    by_type = {}
    for e in entries:
        etype = e.get('type', 'unknown')
        if etype not in by_type:
            by_type[etype] = []
        by_type[etype].append(e)

    lines = ["# Packed Data Index", f"Total: {len(entries)} entries\n"]
    for etype, items in sorted(by_type.items()):
        lines.append(f"## {etype} ({len(items)})")
        for e in items[:5]:  # Top 5 per type
            title = e.get('title', '?')[:80]
            created = e.get('created', '?')[:10]
            tags = e.get('tags', [])
            if isinstance(tags, list):
                tags = tags[:3]
            lines.append(f"- [{created}] {title} `{tags}`")
        if len(items) > 5:
            lines.append(f"- ... and {len(items) - 5} more")
        lines.append("")

    return '\n'.join(lines)

def main():
    if "--index" in sys.argv:
        entries = load_all()
        print(build_index(entries))
        return

    # Parse filters
    ptype = None
    tag = None
    since = None
    search = None
    recent = None
    use_json = "--json" in sys.argv
    do_inject = "--inject" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--type" and i + 1 < len(sys.argv):
            ptype = sys.argv[i + 1]
        if arg == "--tag" and i + 1 < len(sys.argv):
            tag = sys.argv[i + 1]
        if arg == "--since" and i + 1 < len(sys.argv):
            val = sys.argv[i + 1]
            if val.endswith('d'):
                since = datetime.now() - timedelta(days=int(val[:-1]))
            elif val.endswith('h'):
                since = datetime.now() - timedelta(hours=int(val[:-1]))
        if arg == "--search" and i + 1 < len(sys.argv):
            search = sys.argv[i + 1]
        if arg == "--recent" and i + 1 < len(sys.argv):
            recent = int(sys.argv[i + 1])

    entries = load_all()
    results = filter_entries(entries, ptype, tag, since, search, recent)

    if do_inject:
        print(inject_context(results))
    elif use_json:
        output = []
        for r in results:
            output.append({
                "id": r.get("id"), "type": r.get("type"), "title": r.get("title"),
                "created": r.get("created"), "tags": r.get("tags"),
                "file": r.get("_file"), "preview": r.get("_body", "")[:200],
            })
        print(json.dumps({"total": len(results), "results": output}, ensure_ascii=False, indent=2))
    else:
        print(f"PACKED: {len(results)} results")
        for r in results:
            icon = {"research": "🔬", "session": "📝", "error": "🔴", "decision": "✅",
                    "tool-output": "🔧", "memory": "🧠", "insight": "💎"}.get(r.get('type'), '📄')
            created = (r.get('created', '') or '')[:10]
            title = (r.get('title', '?') or '?')[:100]
            tags = r.get('tags', [])
            if isinstance(tags, list):
                tags = tags[:4]
            print(f"  {icon} [{created}] {title}")
            if tags:
                print(f"     tags: {', '.join(tags)}")

if __name__ == "__main__":
    main()
