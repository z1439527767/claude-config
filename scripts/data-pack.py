#!/usr/bin/env python3
"""data-pack — universal data serializer. Converts ANY input into a standardized,
instantly-recognizable storable format with YAML frontmatter + typed body.
Usage:
  echo "data" | python3 data-pack.py --type research    # Research findings
  echo "data" | python3 data-pack.py --type session     # Session notes
  echo "data" | python3 data-pack.py --type error       # Error record
  echo "data" | python3 data-pack.py --type decision    # Decision log
  echo "data" | python3 data-pack.py --type tool-output # Tool output
  python3 data-pack.py --auto < file.txt                # Auto-detect type
  python3 data-pack.py --list                           # List supported types

Output format (universal):
  ---
  id: <type>-<timestamp>-<hash8>
  type: research | session | error | decision | tool-output | memory
  created: 2026-06-25T12:00:00
  tags: [auto-detected]
  source: stdin | file | url
  score: 1.00
  ---
  # Title (auto-generated)
  <typed, structured body>

All output goes to ~/.claude/packed/ directory by default.
"""
import sys, json, os, io, hashlib, re
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
PACK_DIR = HOME / '.claude' / 'packed'
PACK_DIR.mkdir(parents=True, exist_ok=True)

TYPES = {
    "research": {
        "icon": "🔬", "emoji": "📚",
        "template": "## Source\n{source}\n\n## Key Findings\n{body}\n\n## Confidence\n{confidence}",
        "tags": ["research", "findings"],
        "dir": "research",
    },
    "session": {
        "icon": "📝", "emoji": "💾",
        "template": "## Summary\n{summary}\n\n## Changes\n{body}\n\n## Next Steps\n{next}",
        "tags": ["session", "handoff"],
        "dir": "sessions",
    },
    "error": {
        "icon": "🔴", "emoji": "⚠️",
        "template": "## Error\n```\n{body}\n```\n\n## Context\n{context}\n\n## Root Cause\n{root_cause}\n\n## Fix\n{fix}",
        "tags": ["error", "bug"],
        "dir": "errors",
    },
    "decision": {
        "icon": "✅", "emoji": "🎯",
        "template": "## Decision\n{body}\n\n## Alternatives Considered\n{alternatives}\n\n## Rationale\n{rationale}",
        "tags": ["decision", "architecture"],
        "dir": "decisions",
    },
    "tool-output": {
        "icon": "🔧", "emoji": "⚙️",
        "template": "## Command\n```\n{command}\n```\n\n## Output\n```\n{body}\n```\n\n## Exit Code\n{exit_code}",
        "tags": ["tool", "output"],
        "dir": "outputs",
    },
    "memory": {
        "icon": "🧠", "emoji": "💡",
        "template": "## Fact\n{body}\n\n**Why:** {why}\n\n**How to apply:** {how}",
        "tags": ["memory", "knowledge"],
        "dir": "memory",
    },
    "insight": {
        "icon": "💎", "emoji": "✨",
        "template": "## Insight\n{body}\n\n## Evidence\n{evidence}\n\n## Action\n{action}",
        "tags": ["insight", "learning"],
        "dir": "insights",
    },
}

def detect_type(text):
    """Auto-detect the best type for input text."""
    text_lower = text.lower()

    # Error patterns
    if re.search(r'(error|exception|traceback|fail|crash|bug)', text_lower) and len(text) > 50:
        if re.search(r'(Traceback|TypeError|ValueError|SyntaxError|ImportError)', text):
            return "error"

    # Decision patterns
    if re.search(r'(chose|selected|decided|decision|picked|opted|went with)', text_lower):
        if len(text) < 500:
            return "decision"

    # Session patterns
    if re.search(r'(session|commit|changed|modified|created|deleted|updated)', text_lower):
        if re.search(r'(git|file|hook|rule|config)', text_lower):
            return "session"

    # Research patterns
    if re.search(r'(research|study|finding|analysis|comparison|benchmark|survey)', text_lower):
        return "research"

    # Tool output
    if re.search(r'(^\$ |^> |^# |command|exit code|stdout|stderr)', text_lower):
        return "tool-output"

    # Insight
    if re.search(r'(learned|realized|discovered|insight|aha|interesting|notable)', text_lower):
        return "insight"

    # Default: memory
    return "memory"

def extract_metadata(text, ptype):
    """Extract metadata from text based on type."""
    lines = text.strip().split('\n')

    meta = {
        "source": "stdin",
        "confidence": "medium",
        "context": "",
        "root_cause": "",
        "fix": "",
        "alternatives": "",
        "rationale": "",
        "evidence": "",
        "action": "",
        "why": "",
        "how": "",
        "summary": lines[0][:100] if lines else "",
        "next": "",
        "command": "",
        "exit_code": "",
    }

    # Try to extract common fields
    for line in lines:
        l = line.strip()
        if re.match(r'(?i)(source|from|url|origin):\s*', l):
            meta["source"] = re.sub(r'(?i)(source|from|url|origin):\s*', '', l).strip()
        elif re.match(r'(?i)(confidence|score):\s*', l):
            meta["confidence"] = re.sub(r'(?i)(confidence|score):\s*', '', l).strip()
        elif re.match(r'(?i)(root.?cause|原因):\s*', l):
            meta["root_cause"] = re.sub(r'(?i)(root.?cause|原因):\s*', '', l).strip()
        elif re.match(r'(?i)(fix|solution|修复):\s*', l):
            meta["fix"] = re.sub(r'(?i)(fix|solution|修复):\s*', '', l).strip()
        elif re.match(r'(?i)(why|为什么):\s*', l):
            meta["why"] = re.sub(r'(?i)(why|为什么):\s*', '', l).strip()
        elif re.match(r'(?i)(how|怎么):\s*', l):
            meta["how"] = re.sub(r'(?i)(how|怎么):\s*', '', l).strip()
        elif re.match(r'(?i)(rationale|原因|理由):\s*', l):
            meta["rationale"] = re.sub(r'(?i)(rationale|原因|理由):\s*', '', l).strip()
        elif re.match(r'(?i)(evidence|证据):\s*', l):
            meta["evidence"] = re.sub(r'(?i)(evidence|证据):\s*', '', l).strip()
        elif re.match(r'(?i)(action|行动|next):\s*', l):
            meta["action"] = re.sub(r'(?i)(action|行动|next):\s*', '', l).strip()
        elif re.match(r'(?i)(alternative|其他方案):\s*', l):
            meta["alternatives"] = re.sub(r'(?i)(alternative|其他方案):\s*', '', l).strip()

    # Auto-generate summary from first substantial line
    if not meta["summary"]:
        for line in lines:
            l = line.strip()
            if len(l) > 20 and not l.startswith(('#', '```', '$', '>')):
                meta["summary"] = l[:100]
                break

    return meta

def generate_title(text, ptype):
    """Generate a concise, descriptive title."""
    first_line = text.strip().split('\n')[0].strip()
    # Clean up
    first_line = re.sub(r'^[#\-\*\>\$\s]+', '', first_line).strip()
    if len(first_line) > 80:
        first_line = first_line[:77] + '...'
    if len(first_line) < 5:
        first_line = f"{TYPES[ptype]['emoji']} {ptype.title()} entry"
    return first_line

def generate_tags(text, ptype):
    """Auto-detect relevant tags."""
    base_tags = list(TYPES[ptype]["tags"])
    text_lower = text.lower()

    tag_keywords = {
        "python": ["python", "py", "pip", "pytest"],
        "powershell": ["powershell", "pwsh", "ps1", "ps"],
        "git": ["git", "commit", "branch", "merge", "push"],
        "hook": ["hook", "sessionstart", "pretooluse", "posttooluse"],
        "rule": ["rule", "claude.md", "agents.md", "rules/"],
        "tool": ["tool", "script", "cli", "command"],
        "security": ["security", "vuln", "cve", "injection", "secret"],
        "memory": ["memory", "knowledge", "graph", "recall"],
        "performance": ["perf", "slow", "timeout", "optimize"],
        "bug": ["bug", "error", "crash", "fix", "broken"],
    }

    for tag, keywords in tag_keywords.items():
        if any(kw in text_lower for kw in keywords):
            base_tags.append(tag)

    return list(set(base_tags))[:8]  # Max 8 tags

def pack(text, ptype=None, source="stdin"):
    """Main packing function. Returns packed markdown string and metadata."""
    if ptype is None or ptype == "auto":
        ptype = detect_type(text)

    if ptype not in TYPES:
        ptype = "memory"  # fallback

    tinfo = TYPES[ptype]
    meta = extract_metadata(text, ptype)
    title = generate_title(text, ptype)
    tags = generate_tags(text, ptype)

    # Generate unique ID
    hash8 = hashlib.sha256(text.encode()).hexdigest()[:8]
    now = datetime.now()
    entry_id = f"{ptype}-{now.strftime('%Y%m%d-%H%M%S')}-{hash8}"

    # Replace template variables
    body = tinfo["template"].format(
        title=title,
        source=meta["source"],
        body=text.strip(),
        confidence=meta["confidence"],
        context=meta["context"] or "N/A",
        root_cause=meta["root_cause"] or "TBD",
        fix=meta["fix"] or "TBD",
        alternatives=meta["alternatives"] or "N/A",
        rationale=meta["rationale"] or "N/A",
        evidence=meta["evidence"] or "N/A",
        action=meta["action"] or "N/A",
        why=meta["why"] or "TBD",
        how=meta["how"] or "TBD",
        summary=meta["summary"],
        next=meta["next"] or "Continue from last checkpoint",
        command=meta["command"] or "N/A",
        exit_code=meta["exit_code"] or "N/A",
    )

    # Build frontmatter
    fm = f"""---
id: {entry_id}
type: {ptype}
title: {title}
created: {now.isoformat()}
tags: {json.dumps(tags)}
source: {source}
score: 1.00
---

# {tinfo['icon']} {title}
"""
    packed = fm + body

    return {
        "id": entry_id,
        "type": ptype,
        "title": title,
        "tags": tags,
        "packed": packed,
        "file_path": str(PACK_DIR / tinfo["dir"] / f"{entry_id}.md"),
    }

def main():
    if "--list" in sys.argv:
        print("Supported types:")
        for t, info in TYPES.items():
            print(f"  {info['icon']} {t:<15} — {info['template'].split(chr(10))[0][:60]}")
        return

    # Parse arguments
    ptype = "auto"
    source = "stdin"
    output_file = None

    for i, arg in enumerate(sys.argv):
        if arg == "--type" and i + 1 < len(sys.argv):
            ptype = sys.argv[i + 1]
        if arg == "--source" and i + 1 < len(sys.argv):
            source = sys.argv[i + 1]
        if arg == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
        if arg == "--auto":
            ptype = "auto"

    # Read input
    if not sys.stdin.isatty():
        text = sys.stdin.read()
    elif len(sys.argv) > 1 and not sys.argv[-1].startswith('--'):
        # Last arg might be file or text
        candidate = sys.argv[-1]
        if os.path.isfile(candidate):
            text = Path(candidate).read_text(encoding='utf-8', errors='ignore')
            source = candidate
        else:
            text = candidate
    else:
        print(__doc__)
        return

    if not text.strip():
        print("data-pack: no input")
        return

    # Pack it
    result = pack(text, ptype, source)

    # Write to file
    output = Path(output_file) if output_file else Path(result["file_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result["packed"], encoding='utf-8')

    # Report
    print(f"{TYPES[result['type']]['icon']} PACKED: {result['id']}")
    print(f"   type: {result['type']}")
    print(f"   title: {result['title'][:80]}")
    print(f"   tags: {', '.join(result['tags'])}")
    print(f"   file: {output}")

    # Also output the packed content for piping
    if "--stdout" in sys.argv:
        print(f"\n{result['packed']}")

if __name__ == "__main__":
    main()
