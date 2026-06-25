#!/usr/bin/env python3
"""data-bridge — universal data format converter + optimizer.
Transforms data between formats for storage, transmission, and LLM injection.

Three optimization modes:
  store    — maximize information density, YAML frontmatter, gzip-ready structure
  transmit — minimize byte size, strip comments/whitespace, key abbreviation
  inject   — optimize for LLM context window, ~200 token summaries, hierarchical

Pipe-friendly: stdin → transform → stdout
Usage:
  cat data.json | python3 data-bridge.py --from json --to yaml --mode store
  python3 data-bridge.py --from md --to json --mode inject < memory.md
  python3 data-bridge.py --from json --to compact --mode transmit < large.json
  python3 data-bridge.py --auto < input.txt          # Auto-detect format
  python3 data-bridge.py --list-formats              # Show supported formats
"""
import sys, json, os, io, re, csv as csv_mod
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Format Registry ──
SUPPORTED = {
    "json": {"ext": ".json", "desc": "JSON (standard)",
             "detect": lambda s: s.strip().startswith("[") or s.strip().startswith("{")},
    "yaml": {"ext": ".yaml", "desc": "YAML (human-readable)",
             "detect": lambda s: ":" in s and not (s.strip().startswith("[") or s.strip().startswith("{"))},
    "markdown": {"ext": ".md", "desc": "Markdown with frontmatter",
                 "detect": lambda s: s.strip().startswith("---") or s.strip().startswith("#")},
    "csv": {"ext": ".csv", "desc": "CSV (tabular)",
            "detect": lambda s: "," in s.split("\n")[0] if "\n" in s else False},
    "compact": {"ext": ".txt", "desc": "Compact key=value",
                "detect": lambda s: "=" in s and "\n" in s},
    "text": {"ext": ".txt", "desc": "Plain text",
             "detect": lambda s: True},
}

# ── KEY ABBREVIATION MAP (for transmit mode) ──
ABBREV = {
    "description": "d", "created": "c", "updated": "u", "timestamp": "ts",
    "metadata": "m", "confidence": "cf", "source": "src", "target": "tgt",
    "version": "v", "status": "s", "error": "err", "message": "msg",
    "content": "cnt", "title": "t", "tags": "tg", "type": "tp",
    "atomic_id": "aid", "hierarchy": "h", "domain": "dm", "scope": "sc",
}

def auto_detect(text):
    """Auto-detect input format."""
    for fmt, info in SUPPORTED.items():
        if fmt == "text":
            continue
        try:
            if info["detect"](text):
                return fmt
        except Exception:
            pass
    return "text"

def parse_json(text):
    try: return json.loads(text)
    except: return None

def parse_yaml(text):
    """Simple YAML parser (no pyyaml dependency)."""
    result = {}
    lines = text.strip().split('\n')
    stack = [(result, 0)]
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        while stack and indent < stack[-1][1]:
            stack.pop()
        if ':' in stripped:
            k, v = stripped.split(':', 1)
            k, v = k.strip(), v.strip().strip('"\'')
            if v == '' or v == '|':
                v = {}
                stack.append((v, indent + 2))
            elif v.startswith('[') and v.endswith(']'):
                try: v = json.loads(v)
                except: pass
            stack[-1][0][k] = v
    return result

def parse_csv(text):
    try:
        reader = csv_mod.DictReader(io.StringIO(text))
        return list(reader)
    except: return None

def parse_markdown(text):
    """Parse markdown with optional YAML frontmatter."""
    result = {"_format": "markdown", "sections": [], "frontmatter": {}}
    if text.startswith('---'):
        end = text.find('---', 3)
        if end != -1:
            fm_text = text[3:end].strip()
            result["frontmatter"] = parse_yaml(fm_text)
            text = text[end+3:].strip()
    # Extract headings as sections
    sections = re.split(r'\n(?=##?\s)', text)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        heading = re.match(r'(#+)\s+(.+)', sec)
        if heading:
            result["sections"].append({
                "level": len(heading.group(1)),
                "title": heading.group(2),
                "content": sec[heading.end():].strip(),
            })
        else:
            result["sections"].append({"level": 0, "title": "_body", "content": sec})
    return result

def to_json(data, mode="store"):
    if mode == "transmit":
        return json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False, indent=2)

def to_yaml(data, mode="store"):
    """Simple YAML serializer."""
    lines = []
    def _yaml(obj, indent=0):
        prefix = "  " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_str = ABBREV.get(k, k) if mode == "transmit" else k
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k_str}:")
                    _yaml(v, indent + 1)
                elif isinstance(v, bool):
                    lines.append(f"{prefix}{k_str}: {'true' if v else 'false'}")
                elif v is None:
                    lines.append(f"{prefix}{k_str}:")
                else:
                    lines.append(f"{prefix}{k_str}: {v}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    _yaml(item, indent + 1)
                else:
                    lines.append(f"{prefix}- {item}")
    _yaml(data)
    return '\n'.join(lines)

def to_compact(data, mode="store"):
    """Compact key=value format."""
    lines = []
    def _flat(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_str = ABBREV.get(k, k) if mode == "transmit" else k
                full_key = f"{prefix}.{k_str}" if prefix else k_str
                if isinstance(v, (dict, list)):
                    _flat(v, full_key)
                else:
                    lines.append(f"{full_key}={v}")
    _flat(data)
    return '\n'.join(lines)

def to_csv(data, mode="store"):
    """Convert to CSV."""
    if not isinstance(data, list):
        data = [data]
    if not data:
        return ""
    output = io.StringIO()
    writer = csv_mod.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()

def to_inject(data, mode="inject"):
    """Optimize for LLM injection: ~200 token hierarchical summary."""
    lines = []
    token_budget = 200
    token_count = 0

    def _summary(obj, depth=0):
        nonlocal token_count
        prefix = "  " * depth
        if isinstance(obj, dict):
            for k, v in obj.items():
                if token_count > token_budget:
                    return
                if isinstance(v, dict):
                    line = f"{prefix}- {k}: ({len(v)} fields)"
                    token_count += len(line) // 3
                    lines.append(line)
                    if depth < 2:
                        _summary(v, depth + 1)
                elif isinstance(v, list):
                    line = f"{prefix}- {k}: [{len(v)} items]"
                    token_count += len(line) // 3
                    lines.append(line)
                    if depth < 2 and len(v) <= 5:
                        for item in v[:3]:
                            if isinstance(item, str):
                                snippet = str(item)[:80]
                                line2 = f"{prefix}  - {snippet}"
                                token_count += len(line2) // 3
                                lines.append(line2)
                elif v is not None and v != '' and v != '_待補充_' and v != '_待查_':
                    line = f"{prefix}- {k}: {str(v)[:100]}"
                    token_count += len(line) // 3
                    lines.append(line)
        elif isinstance(obj, list):
            line = f"{prefix}[{len(obj)} items]"
            token_count += len(line) // 3
            lines.append(line)
            for item in obj[:3]:
                if isinstance(item, dict):
                    _summary(item, depth + 1)
                elif isinstance(item, str):
                    snippet = str(item)[:80]
                    line2 = f"{prefix}- {snippet}"
                    token_count += len(line2) // 3
                    lines.append(line2)

    _summary(data)
    return '\n'.join(lines)

def optimize_for_mode(data, mode):
    """Strip/transform data based on optimization mode."""
    if mode == "transmit":
        if isinstance(data, dict):
            # Remove verbose fields, keep essentials
            skip_keys = {'_body', '_full_body', '_file', '_preview', 'preview',
                        'how_to_apply', 'alternatives', 'rationale'}
            return {ABBREV.get(k, k): v for k, v in data.items()
                    if k not in skip_keys and v is not None and v != '' and v != '_待補充_'}
    elif mode == "inject":
        if isinstance(data, dict):
            # Keep only high-signal fields
            keep = {'type', 'title', 'description', 'domain', 'created', 'atomic_id', 'score'}
            result = {}
            for k, v in data.items():
                if k in keep and v and v not in ('_待補充_', '_待查_', '_未記錄_'):
                    result[k] = v[:120] if isinstance(v, str) else v
            return result
    return data

def convert(text, from_fmt, to_fmt, mode="store"):
    """Full pipeline: parse → optimize → serialize."""
    # Phase 1: Parse
    parsers = {"json": parse_json, "yaml": parse_yaml, "markdown": parse_markdown,
               "csv": parse_csv, "text": lambda t: {"content": t}}
    parser = parsers.get(from_fmt, lambda t: {"content": t})
    data = parser(text)
    if data is None:
        return f"ERROR: Could not parse as {from_fmt}"

    # Phase 2: Optimize
    data = optimize_for_mode(data, mode)

    # Phase 3: Serialize
    if to_fmt == "inject":
        return to_inject(data, mode)
    serializers = {"json": to_json, "yaml": to_yaml, "compact": to_compact,
                   "csv": to_csv, "text": lambda d, m: str(d)}
    serializer = serializers.get(to_fmt, lambda d, m: str(d))
    return serializer(data, mode)


def main():
    if "--list-formats" in sys.argv:
        print("SUPPORTED FORMATS:\n")
        for fmt, info in SUPPORTED.items():
            print(f"  {fmt:12s} {info['desc']}")
        print("\nMODES: store | transmit | inject")
        return

    from_fmt = "auto"; to_fmt = "yaml"; mode = "store"
    auto = "--auto" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--from" and i + 1 < len(sys.argv):
            from_fmt = sys.argv[i + 1]
        elif arg == "--to" and i + 1 < len(sys.argv):
            to_fmt = sys.argv[i + 1]
        elif arg == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]

    # Read input
    if not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("data-bridge: pipe data via stdin. --list-formats for help.")
        return

    if auto or from_fmt == "auto":
        from_fmt = auto_detect(text)

    result = convert(text, from_fmt, to_fmt, mode)
    print(result)


if __name__ == "__main__":
    main()
