#!/usr/bin/env python3
"""intuition-engine — Ralph's System 1 fast-thinking layer.
Pattern-matching based instant recommendations WITHOUT deep reasoning.
Like human "gut feeling" — recognizes familiar patterns and fires instantly.

Builds a signature index from past experiences:
  Error signatures → known fixes (no need to re-debug)
  File patterns → optimal tools (no need to think)
  Task descriptions → best agent (no need to plan)
  User commands → historical outcomes (no need to guess)

Usage:
  python3 intuition-engine.py --build              # Build/refresh signature index
  python3 intuition-engine.py --query "error X"     # Query intuition for error X
  python3 intuition-engine.py --inject              # Inject top intuitions
  python3 intuition-engine.py --stats               # Show index stats
"""
import sys, json, os, io, re, hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
MEMORY_DIR = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory'
INDEX_FILE = CLAUDE / '.claude' / 'intuition_index.json'

# ── Signature Types ──

def build_error_signatures():
    """Extract error→fix mappings from memory."""
    sigs = {}
    if not MEMORY_DIR.exists():
        return sigs

    for mf in MEMORY_DIR.rglob("*.md"):
        if mf.name == "MEMORY.md" or '_archive' in str(mf):
            continue
        try:
            content = mf.read_text(encoding='utf-8')
            mtype = re.search(r'type:\s*(\S+)', content)
            if mtype and mtype.group(1) in ('error', 'feedback'):
                # Extract error pattern
                err_match = re.search(r'(?:Error|問題|错误)[:：]\s*\n?(.+?)(?=\n##|\n\*\*|\Z)', content, re.DOTALL)
                fix_match = re.search(r'(?:Fix|Root Cause|How to apply|修正)[:：]\s*\n?(.+?)(?=\n##|\n---|\Z)', content, re.DOTALL)
                if err_match:
                    err_key = err_match.group(1).strip()[:80].lower()
                    err_sig = hashlib.sha256(err_key.encode()).hexdigest()[:12]
                    sigs[err_sig] = {
                        "type": "error",
                        "pattern": err_key[:120],
                        "fix": fix_match.group(1).strip()[:200] if fix_match else "See memory file",
                        "source": str(mf.relative_to(MEMORY_DIR)),
                        "confidence": 0.8,
                    }
        except Exception:
            pass
    return sigs

def build_tool_signatures():
    """Extract file→tool mappings from conventions and rules."""
    sigs = {
        hashlib.sha256("powershell script".encode()).hexdigest()[:12]: {
            "type": "tool_choice",
            "pattern": "Editing .ps1 files",
            "fix": "Use Edit tool (not Write) for PowerShell scripts. Verify syntax with PowerShell parser.",
            "confidence": 0.9,
        },
        hashlib.sha256("python script".encode()).hexdigest()[:12]: {
            "type": "tool_choice",
            "pattern": "Creating new Python scripts",
            "fix": "Use Write tool. Add UTF-8 stdout wrapper. Test with python3.",
            "confidence": 0.9,
        },
        hashlib.sha256("config change".encode()).hexdigest()[:12]: {
            "type": "tool_choice",
            "pattern": "Changing agent config/behavior",
            "fix": "Only modify: settings.json, CLAUDE.md, AGENTS.md. Three files only.",
            "confidence": 0.95,
        },
        hashlib.sha256("git operation".encode()).hexdigest()[:12]: {
            "type": "tool_choice",
            "pattern": "Git operations",
            "fix": "Never force-push default branch. Never skip hooks. Commit with Co-Authored-By.",
            "confidence": 0.95,
        },
    }
    return sigs

def build_task_signatures():
    """Extract task→agent mappings from orchestrator patterns."""
    sigs = {
        hashlib.sha256("verify code".encode()).hexdigest()[:12]: {
            "type": "agent_choice",
            "pattern": "Verify/validate/test code changes",
            "fix": "Use engine-verifier agent OR run verify-all.py --quick",
            "confidence": 0.85,
        },
        hashlib.sha256("security check".encode()).hexdigest()[:12]: {
            "type": "agent_choice",
            "pattern": "Security audit or sensitive changes",
            "fix": "Use security-auditor agent. Check for secrets, injection, unsafe ops.",
            "confidence": 0.9,
        },
        hashlib.sha256("research topic".encode()).hexdigest()[:12]: {
            "type": "agent_choice",
            "pattern": "Research or explore new topics",
            "fix": "Use explore agent for broad search, deep-research workflow for thorough analysis.",
            "confidence": 0.85,
        },
    }
    return sigs

def build_lesson_signatures():
    """Extract learned lessons: what NOT to do."""
    sigs = {
        hashlib.sha256("powershell null coalescing".encode()).hexdigest()[:12]: {
            "type": "lesson",
            "pattern": "PowerShell ?? null-coalescing",
            "fix": "?? causes parse errors in some PS parsers. Use if/else instead.",
            "confidence": 0.95,
        },
        hashlib.sha256("powershell cjk pipe".encode()).hexdigest()[:12]: {
            "type": "lesson",
            "pattern": "PowerShell pipe to native exe with CJK",
            "fix": "Pipe to native exe drops CJK encoding. Use argument mode instead.",
            "confidence": 0.95,
        },
        hashlib.sha256("new-item force truncate".encode()).hexdigest()[:12]: {
            "type": "lesson",
            "pattern": "PowerShell New-Item -Force on existing file",
            "fix": "New-Item -Force TRUNCATES existing files. Use if/else not exist check.",
            "confidence": 0.95,
        },
        hashlib.sha256("self evolution vs project".encode()).hexdigest()[:12]: {
            "type": "lesson",
            "pattern": "Evolving self vs modifying user project",
            "fix": "Self-evolution ≠ modifying user projects. Two separate tracks.",
            "confidence": 0.95,
        },
    }
    return sigs

# ── Index Builder ──

def build_index():
    """Build complete intuition index from all sources."""
    index = {
        "built": datetime.now().isoformat(),
        "signatures": {},
    }

    # Merge all signature sources
    for name, builder in [
        ("error", build_error_signatures),
        ("tool", build_tool_signatures),
        ("task", build_task_signatures),
        ("lesson", build_lesson_signatures),
    ]:
        sigs = builder()
        index["signatures"].update(sigs)

    return index

def save_index(index):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')

def load_index():
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return None

# ── Query Engine ──

def query_intuition(query, index=None, top_n=5):
    """Query the intuition index for matching patterns."""
    if index is None:
        index = load_index()

    if not index or not index.get("signatures"):
        return []

    sigs = index["signatures"]
    q = query.lower()

    # Simple keyword matching against patterns
    results = []
    for sig_id, sig in sigs.items():
        pattern = sig.get("pattern", "").lower()
        # Score: exact match > partial keyword match
        score = 0
        if q in pattern:
            score = 1.0
        else:
            # Keyword overlap
            q_words = set(q.split())
            p_words = set(pattern.split())
            overlap = q_words & p_words
            if overlap:
                score = len(overlap) / max(len(q_words), 1) * 0.7

        if score > 0:
            results.append({**sig, "sig_id": sig_id, "score": round(score, 2)})

    # Sort by score * confidence
    results.sort(key=lambda x: -(x["score"] * x.get("confidence", 0.5)))
    return results[:top_n]

def inject_intuition(query=None, max_tokens=200):
    """Generate compact intuition injection for context."""
    index = load_index()
    if not index:
        return ""

    if query:
        results = query_intuition(query, index, top_n=5)
    else:
        # Return top lessons as general intuition
        sigs = index.get("signatures", {})
        results = [s for s in sigs.values() if s.get("type") == "lesson"][:5]

    if not results:
        return ""

    lines = ["## Intuition (fast pattern match)"]
    token_est = 15
    for r in results[:5]:
        icon = {"error": "🔴", "tool_choice": "🔧", "agent_choice": "🤖", "lesson": "📖"}.get(r.get("type", ""), "💡")
        fix = r.get("fix", "")[:120]
        line = f"- {icon} {fix}"
        line_tokens = len(line) // 3
        if token_est + line_tokens > max_tokens:
            break
        lines.append(line)
        token_est += line_tokens
    return '\n'.join(lines)

# ── Stats ──

def index_stats(index):
    if not index:
        return {"status": "no index built"}
    sigs = index.get("signatures", {})
    by_type = Counter(s.get("type", "unknown") for s in sigs.values())
    return {
        "total_signatures": len(sigs),
        "by_type": dict(by_type),
        "built": index.get("built", "unknown"),
        "avg_confidence": round(sum(s.get("confidence", 0) for s in sigs.values()) / max(1, len(sigs)), 2),
    }

def main():
    if "--build" in sys.argv:
        index = build_index()
        save_index(index)
        stats = index_stats(index)
        print(f"INTUITION INDEX BUILT: {stats['total_signatures']} signatures")
        print(f"  By type: {stats['by_type']}")
        print(f"  Avg confidence: {stats['avg_confidence']}")
        return

    if "--rebuild" in sys.argv:
        index = build_index()
        save_index(index)
        print(f"INTUITION: rebuilt — {len(index['signatures'])} signatures")
        return

    if "--stats" in sys.argv:
        index = load_index()
        stats = index_stats(index)
        if "--json" in sys.argv:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print(f"INTUITION INDEX: {stats}")
        return

    if "--inject" in sys.argv:
        query = None
        for i, arg in enumerate(sys.argv):
            if arg == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
        print(inject_intuition(query))
        return

    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        if idx + 1 < len(sys.argv):
            query = sys.argv[idx + 1]
            results = query_intuition(query)
            if not results:
                print("No intuition match. Full reasoning required.")
            else:
                print(f"INTUITION: {len(results)} matches for '{query[:60]}'\n")
                for r in results:
                    icon = {"error": "🔴", "tool_choice": "🔧", "agent_choice": "🤖", "lesson": "📖"}.get(r.get("type", ""), "💡")
                    print(f"  {icon} [{r.get('type')}] ({r['score']:.0%} × {r.get('confidence', 0):.0%})")
                    print(f"     Pattern: {r.get('pattern', '?')[:100]}")
                    print(f"     Fix: {r.get('fix', '?')[:150]}")
            return

    # Default
    index = load_index()
    if not index:
        print("No intuition index. Run --build first.")
        print("Usage: --build | --query '...' | --inject | --stats | --rebuild")
    else:
        print(f"Intuition Index: {len(index['signatures'])} signatures (built {index.get('built', '?')[:10]})")
        print("Usage: --query 'error message' | --inject | --stats | --rebuild")

if __name__ == "__main__":
    main()
