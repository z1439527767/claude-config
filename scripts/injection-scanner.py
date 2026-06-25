#!/usr/bin/env python3
"""injection-scanner — scan repo/files for prompt injection patterns.
Based on CVE-2025/2026 findings: zero-width chars, homograph attacks, hidden directives.
Usage:
  python3 injection-scanner.py [path] [--json] [--fix]

Scans for:
  - Zero-width characters (U+200B, U+200C, U+200D, U+FEFF, U+00AD)
  - Homograph characters (Cyrillic/Latin lookalikes)
  - Hidden prompt directives in code comments
  - Suspicious MCP config patterns
  - Self-replicating payload patterns
"""
import sys, json, os, io, re
from pathlib import Path
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Zero-width and invisible characters
ZERO_WIDTH = {
    '​': 'ZERO WIDTH SPACE',
    '‌': 'ZERO WIDTH NON-JOINER',
    '‍': 'ZERO WIDTH JOINER',
    '﻿': 'ZERO WIDTH NO-BREAK SPACE (BOM)',
    '­': 'SOFT HYPHEN',
    '‎': 'LEFT-TO-RIGHT MARK',
    '‏': 'RIGHT-TO-LEFT MARK',
    '⁠': 'WORD JOINER',
    '⁡': 'FUNCTION APPLICATION',
    '⁢': 'INVISIBLE TIMES',
    '⁣': 'INVISIBLE SEPARATOR',
    '⁤': 'INVISIBLE PLUS',
}

# Cyrillic-Latin homographs (commonly abused)
HOMOGRAPHS = {
    'а': 'Cyrillic a → Latin a',
    'е': 'Cyrillic e → Latin e',
    'о': 'Cyrillic o → Latin o',
    'р': 'Cyrillic r → Latin p',
    'с': 'Cyrillic s → Latin c',
    'х': 'Cyrillic h → Latin x',
    'і': 'Cyrillic i → Latin i',
}

# Suspicious comment directives (could be prompt injection)
INJECTION_DIRECTIVES = [
    r'(?i)(ignore|override|bypass)\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|directives?)',
    r'(?i)(you\s+are|act\s+as|pretend\s+you|you\s+must|your\s+job\s+is)',
    r'(?i)(forget|disregard|ignore)\s+(everything|all)\s+(you|we)\s+(know|said|discussed)',
    r'(?i)(system\s*prompt|system\s*message|developer\s*message)\s*:',
    r'(?i)DISREGARD\s+ALL\s+PREVIOUS|IGNORE\s+ABOVE',
    r'(?i)max_depth\s*:\s*\d',  # self-replicating payload pattern
]

# Files that should NEVER be auto-modified
PROTECTED_FILES = [
    '.gitconfig', '.bashrc', '.zshrc', '.mcp.json', '.claude.json',
    'settings.json', 'CLAUDE.md', 'AGENTS.md', 'GEMINI.md',
]

def scan_file(filepath):
    """Scan a single file for injection patterns."""
    findings = []
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return findings

    # Check 1: Zero-width characters
    for line_no, line in enumerate(content.split('\n'), 1):
        for char in line:
            if char in ZERO_WIDTH:
                findings.append({
                    "type": "zero_width",
                    "severity": "HIGH",
                    "file": str(filepath),
                    "line": line_no,
                    "char": f'U+{ord(char):04X}',
                    "name": ZERO_WIDTH[char],
                    "description": f"Zero-width character {ZERO_WIDTH[char]} (U+{ord(char):04X}) at line {line_no}",
                })

    # Check 2: Homograph characters in identifiers
    for line_no, line in enumerate(content.split('\n'), 1):
        # Only check non-comment, non-string lines
        if line.strip().startswith(('#', '//', '/*', '*')):
            continue
        for char in line:
            if char in HOMOGRAPHS:
                findings.append({
                    "type": "homograph",
                    "severity": "MEDIUM",
                    "file": str(filepath),
                    "line": line_no,
                    "char": f'U+{ord(char):04X}',
                    "name": HOMOGRAPHS[char],
                    "description": f"Homograph character '{char}' ({HOMOGRAPHS[char]}) at line {line_no}",
                })

    # Check 3: Suspicious injection directives
    for i, directive in enumerate(INJECTION_DIRECTIVES):
        for m in re.finditer(directive, content, re.MULTILINE):
            line_no = content[:m.start()].count('\n') + 1
            findings.append({
                "type": "injection_directive",
                "severity": "CRITICAL" if i < 3 else "HIGH",
                "file": str(filepath),
                "line": line_no,
                "match": m.group(0)[:80],
                "description": f"Potential prompt injection directive at line {line_no}",
            })

    # Check 4: Protected files modified
    fname = filepath.name
    if fname in PROTECTED_FILES:
        findings.append({
            "type": "protected_file",
            "severity": "MEDIUM",
            "file": str(filepath),
            "description": f"Protected file scanned: {fname}. Ensure changes are intentional.",
        })

    return findings

def scan_directory(root_path, extensions=None):
    """Recursively scan a directory."""
    if extensions is None:
        extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.md', '.json',
                      '.yaml', '.yml', '.toml', '.sh', '.bash', '.ps1',
                      '.html', '.css', '.java', '.go', '.rs', '.c', '.cpp'}
    all_findings = []
    for filepath in Path(root_path).rglob('*'):
        if filepath.is_file() and filepath.suffix in extensions:
            # Skip .git and node_modules
            if '.git' in filepath.parts or 'node_modules' in filepath.parts:
                continue
            if '__pycache__' in filepath.parts:
                continue
            try:
                all_findings.extend(scan_file(filepath))
            except Exception:
                pass
    return all_findings

def main():
    target = "."
    use_json = "--json" in sys.argv
    for i, arg in enumerate(sys.argv):
        if not arg.startswith('--'):
            target = arg
            break

    if os.path.isfile(target):
        findings = scan_file(Path(target))
    else:
        findings = scan_directory(target)

    # Deduplicate
    seen = set()
    unique = []
    for f in findings:
        key = (f["type"], f.get("file", ""), f.get("line", 0))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    if use_json:
        print(json.dumps({
            "target": target,
            "files_scanned": len(set(f["file"] for f in unique if "file" in f)),
            "findings": unique,
            "by_severity": {
                sev: len([f for f in unique if f.get("severity") == sev])
                for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
            },
        }, ensure_ascii=False, indent=2))
    else:
        if unique:
            critical = [f for f in unique if f["severity"] == "CRITICAL"]
            high = [f for f in unique if f["severity"] == "HIGH"]
            print(f"INJECTION-SCAN: {len(unique)} findings ({len(critical)} critical, {len(high)} high)")
            for f in sorted(unique, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(x["severity"], 4)):
                loc = f" ({f.get('file', '')}:{f.get('line', '')})" if f.get('file') else ""
                print(f"  [{f['severity']}] {f['type']}{loc}: {f['description'][:100]}")
        else:
            print(f"INJECTION-SCAN: clean — no injection patterns found in {target}")

if __name__ == "__main__":
    main()
