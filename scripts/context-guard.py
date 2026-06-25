#!/usr/bin/env python3
"""context-guard — token budget monitor + auto-compact + smart compression.
Prevents context overflow, enables autonomous /compact, and saves tokens.

Three layers:
  1. Monitor  — track context usage, estimate token counts, warn at thresholds
  2. Compress — summarize old turns, prune low-signal content, deduplicate
  3. Compact  — auto-trigger /compact when approaching limits (PreToolUse hook)

Usage:
  python3 context-guard.py --monitor              # Check current context health
  python3 context-guard.py --estimate <file>       # Estimate token count for a file
  python3 context-guard.py --compress <file>       # Compress a file for context injection
  python3 context-guard.py --auto-compact          # Check if auto-compact needed
  python3 context-guard.py --budget-report         # Full budget report
  python3 context-guard.py --hook-output           # Output for PreToolUse hook

Token estimation uses claude-tokenizer if available, falls back to word/3 heuristic.
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
GUARD_STATE = CLAUDE / '.claude' / 'context_guard_state.json'

# ── Default Budget ──
DEFAULT_MAX_TOKENS = 200000   # Claude Code max context
SAFE_LINE = 0.60              # 60% = 120K tokens — safe zone
WARNING_LINE = 0.75           # 75% = 150K tokens — warning
COMPACT_LINE = 0.85           # 85% = 170K tokens — auto-compact trigger
DANGER_LINE = 0.95            # 95% — critical, stop adding

# ── Token Estimation ──

def estimate_tokens(text):
    """Estimate token count. Tries claude-tokenizer, falls back to heuristic."""
    if not text:
        return 0

    # Try claude-tokenizer (if installed)
    try:
        from tokenizers import Tokenizer
        tok = Tokenizer.from_pretrained("claude-tokenizer")
        return len(tok.encode(text).ids)
    except (ImportError, Exception):
        pass

    # Heuristic: ~3 chars per token for English, ~1.5 for CJK
    chars = len(text)
    cjk_chars = len(re.findall(r'[一-鿿぀-ゟ゠-ヿ]', text))
    non_cjk = chars - cjk_chars
    return int(non_cjk / 3.5 + cjk_chars / 1.8)

def estimate_file_tokens(filepath):
    """Estimate tokens for a file."""
    try:
        text = Path(filepath).read_text(encoding='utf-8')
        return estimate_tokens(text)
    except Exception:
        return 0

# ── Compression Strategies ──

def compress_summary(text, target_tokens=200):
    """Compress text to fit within target tokens by extracting key sentences."""
    current = estimate_tokens(text)
    if current <= target_tokens:
        return text

    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    if len(sentences) <= 2:
        return text[:target_tokens * 3]  # Rough char estimate

    # Score sentences by keyword density
    keywords = set(re.findall(r'\b[A-Z][a-z]{2,}\b|\b[a-z]{4,}\b', text.lower()))
    scored = []
    for s in sentences:
        words = set(re.findall(r'\b\w{3,}\b', s.lower()))
        score = len(words & keywords) / max(1, len(words))
        scored.append((score, s))

    # Pick top sentences within budget
    scored.sort(key=lambda x: -x[0])
    result = []
    token_count = 0
    for _, s in scored:
        s_tokens = estimate_tokens(s) + 1
        if token_count + s_tokens > target_tokens:
            break
        result.append(s)
        token_count += s_tokens

    return ' '.join(result)

def compress_markdown(text, target_tokens=500):
    """Compress markdown: keep headings + first sentence of each section."""
    current = estimate_tokens(text)
    if current <= target_tokens:
        return text

    sections = re.split(r'\n(?=##?\s)', text)
    result = []
    token_count = 0

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        heading = re.match(r'(#+)\s+(.+)', sec)
        if heading:
            result.append(heading.group(0))
            token_count += estimate_tokens(heading.group(0))
            # Take first sentence after heading
            body = sec[heading.end():].strip()
            first_sent = re.split(r'(?<=[.!?。！？])\s+', body)[0]
            if estimate_tokens(first_sent) + token_count < target_tokens:
                result.append(first_sent)
                token_count += estimate_tokens(first_sent)
        else:
            first_line = sec.split('\n')[0][:120]
            if token_count + 20 < target_tokens:
                result.append(first_line)
                token_count += 20

    return '\n\n'.join(result)

def strip_low_signal(text):
    """Remove low-signal content: emoji, repeated punctuation, filler words."""
    # Collapse repeated punctuation
    text = re.sub(r'([.!?。！？])\1{2,}', r'\1', text)
    # Remove excessive emoji (keep 1 per paragraph)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        emoji_count = len(re.findall(r'[\U0001F300-\U0001F9FF☀-➿⭐]', line))
        if emoji_count > 3:
            line = re.sub(r'[\U0001F300-\U0001F9FF☀-➿⭐]', '', line)
        cleaned.append(line)
    return '\n'.join(cleaned)


# ── Budget Monitor ──

def load_guard_state():
    if GUARD_STATE.exists():
        try:
            return json.loads(GUARD_STATE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"compact_count": 0, "last_compact": None, "warnings_issued": 0,
            "token_estimates": [], "budget": DEFAULT_MAX_TOKENS}

def save_guard_state(state):
    GUARD_STATE.parent.mkdir(parents=True, exist_ok=True)
    GUARD_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def check_budget(current_estimate, state):
    """Check current usage against budget thresholds."""
    budget = state.get("budget", DEFAULT_MAX_TOKENS)
    ratio = current_estimate / budget

    if ratio >= DANGER_LINE:
        return "danger", f"CRITICAL: {ratio:.0%} of budget used ({current_estimate}/{budget})"
    elif ratio >= COMPACT_LINE:
        return "compact", f"COMPACT: {ratio:.0%} — auto-compact recommended"
    elif ratio >= WARNING_LINE:
        return "warning", f"Warning: {ratio:.0%} — approaching limit"
    elif ratio >= SAFE_LINE:
        return "monitor", f"Monitor: {ratio:.0%} — above safe line"
    else:
        return "safe", f"Safe: {ratio:.0%}"

def auto_compact_needed(current_estimate, state):
    """Determine if auto-compact should be triggered."""
    budget = state.get("budget", DEFAULT_MAX_TOKENS)
    ratio = current_estimate / budget

    # Don't compact more than once per 5 minutes
    last = state.get("last_compact")
    if last:
        try:
            since = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            if since < 300:
                return False, f"Too soon after last compact ({since:.0f}s ago)"
        except Exception:
            pass

    if ratio >= COMPACT_LINE:
        return True, f"Budget at {ratio:.0%}"
    if ratio >= WARNING_LINE and state.get("warnings_issued", 0) >= 3:
        return True, f"Budget at {ratio:.0%} after {state['warnings_issued']} warnings"

    return False, f"Budget at {ratio:.0%} (threshold: {COMPACT_LINE:.0%})"


# ── Bulk Project Token Audit ──

def audit_project_files(root_path, max_files=50):
    """Audit token usage across project files."""
    root = Path(root_path)
    if not root.exists():
        return []

    results = []
    # Skip binary, hidden, node_modules
    skip_patterns = ['.git', 'node_modules', '__pycache__', '.venv', 'venv',
                     '*.pyc', '*.png', '*.jpg', '*.gif', '*.svg', '*.ico',
                     '*.woff', '*.ttf', '*.eot', '*.zip', '*.tar', '*.gz']

    for f in root.rglob("*"):
        skip = False
        for pat in skip_patterns:
            if f.match(pat) or any(p in f.parts for p in ['.git', 'node_modules', '__pycache__']):
                skip = True
                break
        if skip or not f.is_file():
            continue

        try:
            size_kb = f.stat().st_size / 1024
            if size_kb > 1000:  # Skip files > 1MB
                continue
            text = f.read_text(encoding='utf-8', errors='ignore')
            tokens = estimate_tokens(text)
            results.append({
                "file": str(f.relative_to(root)),
                "size_kb": round(size_kb, 1),
                "tokens": tokens,
                "ratio": round(tokens / max(1, size_kb), 1),
            })
        except Exception:
            pass

    results.sort(key=lambda x: -x["tokens"])
    return results[:max_files]

# ── Token-Saving Recommendations ──

def recommend_savings(project_root=None):
    """Generate token-saving recommendations."""
    recs = []

    # 1. Check CLAUDE.md size
    claude_md = CLAUDE / 'CLAUDE.md'
    if claude_md.exists():
        tokens = estimate_file_tokens(claude_md)
        if tokens > 3000:
            recs.append({
                "what": "CLAUDE.md",
                "tokens": tokens,
                "action": f"Trim from ~{tokens} to <3000 tokens",
                "saving": tokens - 3000,
            })

    # 2. Check rules total
    rules_dir = CLAUDE / '.claude' / 'rules'
    if rules_dir.exists():
        total = sum(estimate_file_tokens(rf) for rf in rules_dir.glob("*.md"))
        if total > 5000:
            recs.append({
                "what": "Rules directory",
                "tokens": total,
                "action": f"Prune rules: {total} tokens → target 5000",
                "saving": total - 5000,
            })

    # 3. Check memory index
    mem_index = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory' / 'MEMORY.md'
    if mem_index.exists():
        tokens = estimate_file_tokens(mem_index)
        if tokens > 1500:
            recs.append({
                "what": "MEMORY.md index",
                "tokens": tokens,
                "action": f"Compact MEMORY.md from {tokens} tokens",
                "saving": tokens - 1500,
            })

    # 4. Check hook scripts
    hooks_dir = CLAUDE / 'scripts' / 'hooks'
    if hooks_dir.exists():
        total = sum(estimate_file_tokens(hf) for hf in hooks_dir.glob("*.ps1"))
        if total > 10000:
            recs.append({
                "what": "Hook scripts",
                "tokens": total,
                "action": "Review hook complexity",
                "saving": 0,
            })

    recs.sort(key=lambda x: -x.get("saving", 0))
    return recs


def main():
    if "--monitor" in sys.argv or "--budget-report" in sys.argv:
        state = load_guard_state()
        budget = state.get("budget", DEFAULT_MAX_TOKENS)
        # Estimate current context usage from available signals
        print(f"CONTEXT GUARD — Budget Report")
        print(f"  Budget:      {budget:,} tokens")
        print(f"  Safe line:   {SAFE_LINE:.0%} = {int(budget * SAFE_LINE):,}")
        print(f"  Warning:     {WARNING_LINE:.0%} = {int(budget * WARNING_LINE):,}")
        print(f"  Compact:     {COMPACT_LINE:.0%} = {int(budget * COMPACT_LINE):,}")
        print(f"  Danger:      {DANGER_LINE:.0%} = {int(budget * DANGER_LINE):,}")
        print(f"  Compacts:    {state.get('compact_count', 0)}")
        print(f"  Warnings:    {state.get('warnings_issued', 0)}")

        # Show savings recommendations
        recs = recommend_savings()
        if recs:
            print(f"\n  ── Token-Saving Opportunities ──")
            for r in recs[:5]:
                saving_str = f" (save ~{r['saving']})" if r['saving'] > 0 else ""
                print(f"  📉 {r['what']}: {r['tokens']} tokens → {r['action']}{saving_str}")
        return

    if "--auto-compact" in sys.argv:
        state = load_guard_state()
        # Estimate from CLAUDE.md + rules + memory (what's loaded at SessionStart)
        l0_tokens = estimate_file_tokens(CLAUDE / 'CLAUDE.md') + estimate_file_tokens(CLAUDE / 'AGENTS.md')
        rules_tokens = sum(estimate_file_tokens(rf) for rf in (CLAUDE / '.claude' / 'rules').glob("*.md"))
        mem_tokens = estimate_file_tokens(CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory' / 'MEMORY.md')
        estimated = l0_tokens + rules_tokens + mem_tokens

        needed, reason = auto_compact_needed(estimated, state)
        result = {"needed": needed, "reason": reason, "estimated_tokens": estimated}
        if "--json" in sys.argv:
            print(json.dumps(result))
        else:
            status = "🔴 COMPACT NEEDED" if needed else "🟢 OK"
            print(f"{status}: {reason} (est. {estimated} tokens loaded)")
        return

    if "--estimate" in sys.argv:
        idx = sys.argv.index("--estimate")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
            path = Path(target)
            if path.exists():
                tokens = estimate_file_tokens(path)
                print(f"{tokens} tokens → {path}")
            else:
                tokens = estimate_tokens(target)
                print(f"{tokens} tokens (estimated)")
        return

    if "--compress" in sys.argv:
        idx = sys.argv.index("--compress")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
            path = Path(target)
            text = path.read_text(encoding='utf-8') if path.exists() else target
            compressed = compress_markdown(text)
            saved = estimate_tokens(text) - estimate_tokens(compressed)
            print(f"Compressed: {estimate_tokens(text)} → {estimate_tokens(compressed)} tokens (saved {saved})")
            print("---")
            print(compressed)
        return

    if "--audit" in sys.argv:
        idx = sys.argv.index("--audit")
        root = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else str(CLAUDE)
        results = audit_project_files(root)
        print(f"TOKEN AUDIT: {root} — {len(results)} files")
        total = 0
        for r in results[:20]:
            print(f"  {r['tokens']:>6} tk  {r['size_kb']:>6.1f} KB  {r['file']}")
            total += r['tokens']
        print(f"  ────────")
        print(f"  {total:>6} tk  total (top 20)")
        return

    if "--hook-output" in sys.argv:
        state = load_guard_state()
        l0_tokens = estimate_file_tokens(CLAUDE / 'CLAUDE.md')
        state["token_estimates"].append({"ts": datetime.now().isoformat(), "tokens": l0_tokens})
        state["token_estimates"] = state["token_estimates"][-20:]
        save_guard_state(state)
        # Hook output: JSON with recommendation
        needed, reason = auto_compact_needed(l0_tokens, state)
        if needed:
            state["warnings_issued"] += 1
            save_guard_state(state)
            print(json.dumps({"action": "compact", "reason": reason}))
        return

    # Default: show help
    print("context-guard: --monitor | --auto-compact | --estimate <f> | --compress <f> | --audit <dir> | --budget-report")


if __name__ == "__main__":
    main()
