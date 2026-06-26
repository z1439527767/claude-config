#!/usr/bin/env python3
"""memory-create — standardized memory file creation with auto-indexing + KG sync.
Usage:
  echo "content" | python3 memory-create.py --type feedback --title "Fix: X"
  python3 memory-create.py --type reference --title "API docs" --content "URL: ..."
  python3 memory-create.py --type insight --title "Pattern found" --file notes.txt
  python3 memory-create.py --list-types          # List valid types + hierarchies
  python3 memory-create.py --validate            # Validate all existing memory files

Frontmatter standard (agentskills.io compatible):
  name: kebab-slug (auto-generated from title)
  description: one-line summary
  metadata:
    node_type: memory
    hierarchy: root | branch | leaf | distilled
    node_path: <hierarchy>/<filename>.md
    type: preference | feedback | project | reference | error | insight | decision
    domain: behavior | memory | infrastructure | security | ...
    scope: global | project:<name>
    condition: when to apply this memory
    confidence: high | medium | low
    atomic_id: <prefix>-<timestamp>-<hash6>
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    originSessionId: <uuid>
    access_count: 0
    last_accessed: <iso-datetime>
"""
import sys, json, os, io, re, hashlib, uuid
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
MEMORY_DIR = HOME / '.claude' / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'
MEMORY_INDEX = MEMORY_DIR / 'MEMORY.md'
STATE_FILE = HOME / '.claude' / '.claude' / 'memory_scores.json'

# ── Type Registry ──
VALID_TYPES = {
    "preference": {"hierarchy": "branch", "prefix": "pref", "domain": "behavior",
                   "template": "## Preference\n\n{body}\n\n**Why:** {why}\n\n**How to apply:** {how}"},
    "feedback":   {"hierarchy": "leaf", "prefix": "fb", "domain": "behavior",
                   "template": "## Context\n\n{body}\n\n**Why:** {why}\n\n**How to apply:** {how}"},
    "project":    {"hierarchy": "leaf", "prefix": "proj", "domain": "project",
                   "template": "## Project State\n\n{body}"},
    "reference":  {"hierarchy": "leaf", "prefix": "ref", "domain": "infrastructure",
                   "template": "## Reference\n\n{body}"},
    "error":      {"hierarchy": "leaf", "prefix": "err", "domain": "infrastructure",
                   "template": "## Error\n\n```\n{body}\n```\n\n## Root Cause\n{root_cause}\n\n## Fix\n{fix}"},
    "insight":    {"hierarchy": "leaf", "prefix": "ins", "domain": "memory",
                   "template": "## Insight\n\n{body}\n\n**Why:** {why}"},
    "decision":   {"hierarchy": "leaf", "prefix": "dec", "domain": "project",
                   "template": "## Decision\n\n{body}\n\n## Alternatives Considered\n{alternatives}\n\n## Rationale\n{rationale}"},
}

HIERARCHY_LIMITS = {"root": 10, "branch": 20, "leaf": 30, "distilled": 15}

def slugify(text):
    """Convert text to kebab-case slug."""
    s = text.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-{2,}', '-', s)
    return s.strip('-')[:64]

def make_atomic_id(ptype, title):
    """Generate atomic_id: <prefix>-<YYYYMMDD>-<hash6>"""
    prefix_map = {t: info["prefix"] for t, info in VALID_TYPES.items()}
    prefix = prefix_map.get(ptype, "gen")
    ts = datetime.now().strftime("%Y%m%d")
    h = hashlib.sha256(f"{ptype}{title}{datetime.now().isoformat()}".encode()).hexdigest()[:6]
    return f"{prefix}-{ts}-{h}"

def make_filename(atomic_id, title):
    """Generate filename from atomic_id + slugified title."""
    slug = slugify(title)
    return f"{atomic_id}-{slug}.md" if slug else f"{atomic_id}.md"

def build_frontmatter(name, description, metadata):
    """Build YAML frontmatter string."""
    lines = ["---", f"name: {name}", f"description: {description}"]
    # Flatten metadata to top-level for simpler YAML (agentskills.io compatible)
    for k, v in metadata.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for sk, sv in v.items():
                lines.append(f"  {sk}: {sv}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)

def build_body(ptype, body, extras):
    """Build memory body from template + extras."""
    info = VALID_TYPES.get(ptype, {})
    template = info.get("template", "{body}")
    try:
        return template.format(body=body, **extras)
    except KeyError:
        return body

def create_memory(ptype, title, body, hierarchy=None, domain=None, scope="global",
                  condition="", confidence="medium", why="", how="", root_cause="",
                  fix="", alternatives="", rationale="", origin_session=None):
    """Create a new memory file. Returns path relative to MEMORY_DIR."""
    if ptype not in VALID_TYPES:
        print(f"ERROR: Unknown type '{ptype}'. Valid: {', '.join(VALID_TYPES)}")
        return None

    info = VALID_TYPES[ptype]
    if hierarchy is None:
        hierarchy = info["hierarchy"]
    if domain is None:
        domain = info["domain"]

    # Check hierarchy limit
    existing = count_by_hierarchy(hierarchy)
    limit = HIERARCHY_LIMITS.get(hierarchy, 30)
    if existing >= limit:
        print(f"WARNING: {hierarchy} hierarchy at limit ({existing}/{limit}). Consider pruning first.")

    atomic_id = make_atomic_id(ptype, title)
    filename = make_filename(atomic_id, title)
    rel_path = f"{hierarchy}/{filename}"
    filepath = MEMORY_DIR / rel_path

    name = slugify(title)
    now = datetime.now()
    session_id = origin_session or str(uuid.uuid4())[:8]

    # Build extras for template
    extras = {"why": why or "_待补充_", "how": how or "_待补充_",
              "root_cause": root_cause or "_待查_", "fix": fix or "_待实施_",
              "alternatives": alternatives or "_未记录_", "rationale": rationale or "_未记录_"}

    metadata = {
        "node_type": "memory",
        "hierarchy": hierarchy,
        "node_path": rel_path,
        "type": ptype,
        "domain": domain,
        "scope": scope,
        "condition": condition or "always",
        "confidence": confidence,
        "atomic_id": atomic_id,
        "created": now.strftime("%Y-%m-%d"),
        "updated": now.strftime("%Y-%m-%d"),
        "originSessionId": session_id,
        "access_count": 0,
        "last_accessed": now.strftime("%Y-%m-%d %H:%M"),
    }

    frontmatter = build_frontmatter(name, title, metadata)
    body_text = build_body(ptype, body, extras)
    content = f"{frontmatter}\n\n{body_text}\n"

    # Write file
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding='utf-8')

    # Update MEMORY.md index
    update_index(atomic_id, rel_path, title)

    # Update scoring state
    update_scoring_state(atomic_id, now)

    return {"atomic_id": atomic_id, "path": rel_path, "file": str(filepath)}

def count_by_hierarchy(hierarchy):
    """Count existing memories in a hierarchy level."""
    d = MEMORY_DIR / hierarchy
    if not d.exists():
        return 0
    return len([f for f in d.glob("*.md") if f.name != "MEMORY.md"])

def update_index(atomic_id, rel_path, title):
    """Add entry to MEMORY.md index under the correct section."""
    if not MEMORY_INDEX.exists():
        print("WARNING: MEMORY.md not found, cannot update index")
        return

    content = MEMORY_INDEX.read_text(encoding='utf-8')
    hierarchy = rel_path.split('/')[0]

    section_map = {
        "root": "## Root (Core Invariants)",
        "branch": "## Branch (Active Topics)",
        "leaf": "## Leaf (Specific Facts)",
        "distilled": "## Distilled (Merged Memories)",
    }
    section_header = section_map.get(hierarchy, "## Leaf (Specific Facts)")

    entry_line = f"- [{atomic_id}]({rel_path}) — {title} [1.00 fresh]"

    # Insert after the section header
    lines = content.split('\n')
    new_lines = []
    inserted = False
    for i, line in enumerate(lines):
        new_lines.append(line)
        if line.strip() == section_header:
            # Skip the description comment line
            pass
        elif not inserted and i > 0 and lines[i-1].strip() == section_header:
            # Insert after the blank line following section header + comment
            # Find the next blank line
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            # Insert our entry after the comment, before existing entries
            new_lines.append(entry_line)
            inserted = True

    if not inserted:
        new_lines.append(f"\n{section_header}")
        new_lines.append(f"> _auto-generated_")
        new_lines.append("")
        new_lines.append(entry_line)

    # Update total count
    result = '\n'.join(new_lines)
    old_count = content.count('- [')
    new_count = result.count('- [')
    result = result.replace(
        f"總條數：{old_count}",
        f"總條數：{new_count}"
    )
    result = result.replace(
        f"總條數：{old_count - 1}",
        f"總條數：{new_count}"
    )

    # Update last-modified timestamp
    today = datetime.now().strftime('%Y-%m-%d')
    result = re.sub(r'最後更新：\d{4}-\d{2}-\d{2}', f'最後更新：{today}', result)

    MEMORY_INDEX.write_text(result, encoding='utf-8')

def update_scoring_state(atomic_id, now=None):
    """Initialize scoring state for new memory."""
    if not STATE_FILE.exists():
        return
    try:
        state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        state = {}

    if atomic_id not in state:
        ts = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
        state[atomic_id] = {
            "access_count": 0,
            "last_access": ts,
            "applied_successfully": False
        }
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def validate_all():
    """Validate all existing memory files for frontmatter completeness."""
    if not MEMORY_DIR.exists():
        print("No memory directory found")
        return []

    issues = []
    required_fields = ["name", "description", "node_type", "hierarchy", "type", "atomic_id", "created"]
    valid_hierarchies = set(HIERARCHY_LIMITS.keys())

    for md_file in MEMORY_DIR.rglob("*.md"):
        if md_file.name == "MEMORY.md":
            continue
        try:
            content = md_file.read_text(encoding='utf-8')
            if not content.startswith('---'):
                issues.append({"file": str(md_file.relative_to(MEMORY_DIR)), "issue": "no frontmatter"})
                continue

            end = content.find('---', 3)
            if end == -1:
                issues.append({"file": str(md_file.relative_to(MEMORY_DIR)), "issue": "unclosed frontmatter"})
                continue

            fm = content[3:end]
            for field in required_fields:
                if field not in fm:
                    issues.append({"file": str(md_file.relative_to(MEMORY_DIR)), "issue": f"missing field: {field}"})

            # Check hierarchy matches directory
            rel = md_file.relative_to(MEMORY_DIR)
            hier = str(rel.parts[0]) if len(rel.parts) > 1 else ""
            if hier not in valid_hierarchies:
                issues.append({"file": str(rel), "issue": f"invalid hierarchy dir: {hier}"})
            elif f"hierarchy: {hier}" not in fm:
                issues.append({"file": str(rel), "issue": f"hierarchy mismatch: dir={hier}"})

        except Exception as e:
            issues.append({"file": str(md_file.relative_to(MEMORY_DIR)), "issue": str(e)})

    return issues

def list_types():
    """Print valid types and their defaults."""
    print("VALID MEMORY TYPES:\n")
    for t, info in VALID_TYPES.items():
        print(f"  {info['prefix']:6s} → {t:12s}  hierarchy={info['hierarchy']:10s}  domain={info['domain']}")
    print(f"\nHIERARCHY LIMITS:")
    for h, limit in HIERARCHY_LIMITS.items():
        current = count_by_hierarchy(h)
        print(f"  {h:12s}: {current}/{limit}")

def main():
    if "--list-types" in sys.argv:
        list_types()
        return

    if "--validate" in sys.argv:
        issues = validate_all()
        if not issues:
            print("All memory files valid ✓")
        else:
            print(f"{len(issues)} issues found:")
            for i in issues:
                print(f"  ✗ {i['file']}: {i['issue']}")
        return

    # Parse args
    ptype = None; title = None; body = None; file_path = None
    hierarchy = None; domain = None; scope = "global"; condition = ""
    confidence = "medium"; why = ""; how = ""; root_cause = ""
    fix = ""; alternatives = ""; rationale = ""; origin_session = None
    dry_run = "--dry-run" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--type" and i + 1 < len(sys.argv):
            ptype = sys.argv[i + 1]
        elif arg == "--title" and i + 1 < len(sys.argv):
            title = sys.argv[i + 1]
        elif arg == "--content" and i + 1 < len(sys.argv):
            body = sys.argv[i + 1]
        elif arg == "--file" and i + 1 < len(sys.argv):
            file_path = sys.argv[i + 1]
        elif arg == "--hierarchy" and i + 1 < len(sys.argv):
            hierarchy = sys.argv[i + 1]
        elif arg == "--domain" and i + 1 < len(sys.argv):
            domain = sys.argv[i + 1]
        elif arg == "--scope" and i + 1 < len(sys.argv):
            scope = sys.argv[i + 1]
        elif arg == "--confidence" and i + 1 < len(sys.argv):
            confidence = sys.argv[i + 1]
        elif arg == "--why" and i + 1 < len(sys.argv):
            why = sys.argv[i + 1]
        elif arg == "--how" and i + 1 < len(sys.argv):
            how = sys.argv[i + 1]
        elif arg == "--root-cause" and i + 1 < len(sys.argv):
            root_cause = sys.argv[i + 1]
        elif arg == "--fix" and i + 1 < len(sys.argv):
            fix = sys.argv[i + 1]
        elif arg == "--session" and i + 1 < len(sys.argv):
            origin_session = sys.argv[i + 1]

    # Get body from file or stdin
    if file_path:
        try:
            body = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            print(f"ERROR reading file: {e}")
            return
    elif not body and not sys.stdin.isatty():
        body = sys.stdin.read().strip()

    if not ptype or not title:
        print("USAGE: memory-create.py --type <type> --title <title> [--content <text>|--file <path>|stdin]")
        print("       memory-create.py --list-types")
        print("       memory-create.py --validate")
        print(f"\nValid types: {', '.join(VALID_TYPES)}")
        return

    if not body:
        body = title  # Fallback: use title as body
        print("WARNING: No content provided, using title as body")

    if dry_run:
        atomic_id = make_atomic_id(ptype, title)
        filename = make_filename(atomic_id, title)
        info = VALID_TYPES.get(ptype, {})
        hier = hierarchy or info.get("hierarchy", "leaf")
        print(f"DRY RUN:")
        print(f"  atomic_id: {atomic_id}")
        print(f"  file: {hier}/{filename}")
        print(f"  type: {ptype}")
        print(f"  title: {title}")
        return

    result = create_memory(
        ptype=ptype, title=title, body=body,
        hierarchy=hierarchy, domain=domain, scope=scope,
        condition=condition, confidence=confidence,
        why=why, how=how, root_cause=root_cause,
        fix=fix, alternatives=alternatives, rationale=rationale,
        origin_session=origin_session,
    )

    if result:
        print(f"MEMORY CREATED:")
        print(f"  id:   {result['atomic_id']}")
        print(f"  file: {result['path']}")
        print(f"  type: {ptype}")
        print(f"  size: {Path(result['file']).stat().st_size} bytes")

if __name__ == "__main__":
    main()
