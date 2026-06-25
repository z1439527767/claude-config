#!/usr/bin/env python3
"""guess-code-lang — betlang equivalent via ELD-C: detect programming vs natural language.
Uses heuristics: if text contains code patterns, classify as programming language.
Falls back to ELD-C for natural language detection."""
import sys
import re
import eldc

CODE_PATTERNS = {
    "python": [r"\bdef\s+\w+\s*\(.*\)\s*:", r"\bimport\s+\w+", r"\bclass\s+\w+.*:", r"\bprint\s*\(", r"\bfrom\s+\w+\s+import"],
    "javascript": [r"\bconst\s+\w+\s*=", r"\blet\s+\w+\s*=", r"\bfunction\s+\w+\s*\(", r"\bconsole\.log\s*\(", r"=>\s*{"],
    "rust": [r"\bfn\s+\w+\s*\(", r"\blet\s+mut\b", r"\bprintln!\s*\(", r"\bimpl\s+\w+"],
    "go": [r"\bfunc\s+\w+\s*\(", r"\bpackage\s+\w+", r"\bgo\s+func\b", r":=\s+"],
    "java": [r"\bpublic\s+(class|static|void)\b", r"\bSystem\.out\.print", r"\bprivate\s+\w+\s+\w+\s*;"],
    "cpp": [r"#include\s*[<\"']", r"\bstd::\w+", r"\bint\s+main\s*\(", r"->\s*\w+"],
    "sql": [r"\bSELECT\s+.+\s+FROM\b", r"\bINSERT\s+INTO\b", r"\bCREATE\s+TABLE\b", r"\bALTER\s+TABLE\b"],
    "powershell": [r"\bparam\s*\(", r"\$\w+\s*=", r"\bWrite-(Output|Host|Error)\b", r"\bGet-\w+", r"\bforeach\s*\$\w+"],
    "shell": [r"^#!/bin/(ba)?sh", r"\b(chmod|grep|awk|sed)\s+", r"\$\{?\w+\}?"],
    "html": [r"<(!DOCTYPE|html|div|span|head|body)\b"],
    "css": [r"[.#]\w+\s*\{[^}]*\}", r"\b(margin|padding|color|font-size)\s*:"],
    "markdown": [r"^#\s+.+", r"\[.+\]\(.+\)", r"^>\s+"],
    "yaml": [r"^\w+:\s*(|\||\w+$)", r"^\s+-\s+\w+"],
    "json": [r'^\s*\{[\s\n]*"\w+"\s*:', r'^\s*\[[\s\n]*\{', r'"\w+":\s*("[^"]*"|\d+|true|false|null|\{|\[)'],
    "toml": [r'^\w+\s*=\s*[\"\[]', r"\[.*\]\s*$"],
}

def detect_code(text):
    scores = {}
    for lang, patterns in CODE_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text, re.MULTILINE))
        if score > 0:
            scores[lang] = score
    if scores:
        return max(scores, key=scores.get)
    return None

def main():
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
    if not text.strip():
        print("empty"); sys.exit(1)

    code_lang = detect_code(text)
    if code_lang:
        print(code_lang)
        return

    eldc.init()
    print(eldc.detect(text.strip()))

if __name__ == "__main__":
    main()
