#!/usr/bin/env python3
"""scan-project — detect all languages (code + natural) in a directory tree.
Usage: python3 scan-project.py [path]"""
import sys
from collections import Counter
from pathlib import Path
import eldc

SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'target', 'dist', 'build', '.next', 'cache'}
SKIP_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.mp3', '.mp4', '.zip', '.gz', '.tar', '.exe', '.dll', '.so', '.dylib', '.bin', '.pdf'}
MAX_FILE_KB = 256

def detect_code_lang(text):
    import re
    patterns = {
        "python": [r"\bdef\s+\w+\s*\(.*\)\s*:", r"\bimport\s+\w+", r"\bclass\s+\w+.*:", r"\bfrom\s+\w+\s+import"],
        "javascript": [r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bfunction\s+\w+\s*\(", r"=>\s*{"],
        "typescript": [r":\s*(string|number|boolean|void)\b", r"\binterface\s+\w+\s*{"],
        "rust": [r"\bfn\s+\w+\s*\(", r"\blet\s+mut\b", r"\bimpl\s+\w+"],
        "go": [r"\bfunc\s+\w+\s*\(", r"\bpackage\s+\w+", r":=\s+"],
        "java": [r"\bpublic\s+(class|static|void)\b", r"\bSystem\.out\.print"],
        "cpp": [r"#include\s*[<\"']", r"\bstd::\w+", r"\bint\s+main\s*\("],
        "sql": [r"\bSELECT\s+.+\s+FROM\b", r"\bCREATE\s+TABLE\b"],
        "powershell": [r"\bparam\s*\(", r"\bWrite-(Output|Host|Error)\b", r"\bGet-\w+"],
        "shell": [r"^#!/bin/(ba)?sh", r"\b(chmod|grep|awk|sed)\s+"],
        "html": [r"<(!DOCTYPE|html|div|span|head|body)\b"],
        "css": [r"[.#]\w+\s*\{[^}]*\}", r"\b(margin|padding|color)\s*:"],
        "json": [r'"\w+":\s*("[^"]*"|\d+|true|false|null|\{|\[)'],
        "yaml": [r"^\w+:\s*(|\||\w+$)", r"^\s+-\s+\w+"],
        "markdown": [r"^#\s+.+", r"\[.+\]\(.+\)", r"^>\s+"],
        "toml": [r'^\w+\s*=\s*[\"\[]', r"\[.*\]\s*$"],
    }
    scores = {}
    for lang, pats in patterns.items():
        s = sum(1 for p in pats if re.search(p, text, re.MULTILINE))
        if s > 0:
            scores[lang] = s
    return max(scores, key=scores.get) if scores else None

def scan_project(root):
    root = Path(root)
    code_langs = Counter()
    natural_langs = Counter()
    files_scanned = 0
    files_skipped = 0

    eldc.init()

    for fpath in root.rglob('*'):
        if not fpath.is_file():
            continue
        if any(d in fpath.parts for d in SKIP_DIRS):
            continue
        if fpath.suffix.lower() in SKIP_EXTS:
            continue
        if fpath.stat().st_size > MAX_FILE_KB * 1024:
            continue

        try:
            text = fpath.read_text(encoding='utf-8', errors='ignore')[:2000]
        except Exception:
            files_skipped += 1
            continue

        if not text.strip():
            files_skipped += 1
            continue

        files_scanned += 1

        # Code detection
        code = detect_code_lang(text)
        if code:
            code_langs[code] += 1

        # Natural language detection (first non-code line)
        lines = [l for l in text.split('\n') if l.strip() and not l.strip().startswith(('#', '//', '/*', '*', '<!--'))]
        if lines:
            try:
                nat = eldc.detect(lines[0][:500])
                if nat != 'und':
                    natural_langs[nat] += 1
            except Exception:
                pass

    return {
        'files_scanned': files_scanned,
        'files_skipped': files_skipped,
        'code_languages': code_langs.most_common(10),
        'natural_languages': natural_langs.most_common(5),
    }

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = scan_project(path)
    print(f"Scanned: {result['files_scanned']} files ({result['files_skipped']} skipped)")
    print(f"\nCode languages:")
    for lang, count in result['code_languages']:
        print(f"  {lang:15s} {count:4d}")
    print(f"\nNatural languages in comments/docs:")
    for lang, count in result['natural_languages']:
        print(f"  {lang:5s} {count:4d}")
