#!/usr/bin/env python3
"""memory-consolidator v2 — autoDream equivalent: deduplicate, distill, archive, prune.
Three-gate trigger: 24h since last run, 5+ sessions since last, lock acquired.
Usage:
  python3 memory-consolidator.py [--dry-run] [--json] [--force] [--distill] [--archive]

Phases:
  1. Orient — read all memory files, score freshness
  2. Gather — detect duplicates, stale, expired
  3. Consolidate — merge duplicates, distill principles, archive expired
  4. Prune — keep MEMORY.md under 200 lines, rebuild index
"""
import sys, json, os, io, re, hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
MEMORY_DIR = HOME / '.claude' / 'projects' / 'C--Users-z1439--claude' / 'memory'
MEMORY_INDEX = MEMORY_DIR / 'MEMORY.md'
STATE_FILE = HOME / '.claude' / '.claude' / 'consolidator_state.json'
LOCK_FILE = HOME / '.claude' / '.claude' / 'consolidator.lock'
ARCHIVE_DIR = MEMORY_DIR / '_archive'
DISTILLED_DIR = MEMORY_DIR / 'distilled'
MAX_LINES = 200
MAX_SIZE_KB = 25

# ── Keywords for theme grouping ──
THEME_KEYWORDS = {
    'behavior': ['行为', '規則', '不准', '約束', '配置', '三文件', '過度', '簡單', '複雜'],
    'memory': ['記憶', 'memory', '衰减', 'decay', 'Ebbinghaus', '評分', 'score', '蒸馏', '索引'],
    'tool': ['工具', 'tool', 'MCP', 'hook', '脚本', 'script', 'CLI'],
    'error': ['錯誤', 'error', 'bug', '失敗', 'fail', '修復', 'fix', '根因'],
    'session': ['會話', 'session', '教訓', 'lesson', '經驗', '反省'],
    'project': ['項目', 'project', '範圍', 'scope', '邊界', '隔離'],
}

def acquire_lock():
    if LOCK_FILE.exists():
        age = datetime.now() - datetime.fromtimestamp(LOCK_FILE.stat().st_mtime)
        if age.total_seconds() < 300:
            return False
    LOCK_FILE.write_text(datetime.now().isoformat())
    return True

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"last_run": None, "sessions_since": 0, "total_runs": 0, "distilled_count": 0, "archived_count": 0}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def should_run(state, force=False):
    if force:
        return True, "forced"
    if not state["last_run"]:
        return True, "first_run"
    last = datetime.fromisoformat(state["last_run"])
    hours_since = (datetime.now() - last).total_seconds() / 3600
    if hours_since < 24:
        return False, f"time_gate: {hours_since:.1f}h (< 24h)"
    if state["sessions_since"] < 5:
        return False, f"session_gate: {state['sessions_since']} sessions (< 5)"
    return True, "all_gates_passed"

def parse_memory_file(filepath):
    """Parse a memory file — returns dict with frontmatter + body."""
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
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip().strip('"')
    meta["_file"] = str(filepath)
    meta["_body"] = body
    meta["_rel"] = str(filepath.relative_to(MEMORY_DIR)) if MEMORY_DIR in filepath.parents else str(filepath.name)
    return meta

def load_all_memories():
    """Load all memory files."""
    if not MEMORY_DIR.exists():
        return []
    memories = []
    for md_file in MEMORY_DIR.rglob("*.md"):
        if md_file.name == "MEMORY.md" or '_archive' in str(md_file):
            continue
        mem = parse_memory_file(md_file)
        if mem:
            memories.append(mem)
    return memories

def score_memory(mem):
    """Calculate Ebbinghaus score."""
    created_str = mem.get('created', '')
    now = datetime.now()
    try:
        created_dt = datetime.fromisoformat(created_str)
    except Exception:
        created_dt = now
    days = max(0, (now - created_dt).days)
    score = min(1.0, pow(2.71828, -days / 30))
    if days >= 60:
        score *= 0.5
    elif days >= 30:
        score *= 0.75
    return round(score, 2)

def find_theme(mem):
    """Map memory to its dominant theme."""
    desc = mem.get('description', '').lower()
    body = mem.get('_body', '').lower()
    text = f"{desc} {body}"
    scores = {}
    for theme, keywords in THEME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scores[theme] = score
    if not scores:
        return 'general'
    return max(scores, key=lambda k: scores[k])

def find_duplicates(memories):
    """Detect duplicate or near-duplicate memories by description similarity."""
    duplicates = []
    for i, m1 in enumerate(memories):
        for j, m2 in enumerate(memories):
            if j <= i:
                continue
            d1 = m1.get('description', '')
            d2 = m2.get('description', '')
            # Simple Jaccard on words
            w1 = set(d1.lower().split())
            w2 = set(d2.lower().split())
            if not w1 or not w2:
                continue
            jaccard = len(w1 & w2) / len(w1 | w2)
            if jaccard > 0.6:
                duplicates.append({
                    "mem1": m1.get('atomic_id', m1.get('_rel')),
                    "mem2": m2.get('atomic_id', m2.get('_rel')),
                    "similarity": round(jaccard, 2),
                    "desc1": d1[:80],
                    "desc2": d2[:80],
                })
    return duplicates

def find_stale(memories):
    """Find stale and expired memories."""
    stale = []
    for mem in memories:
        score = score_memory(mem)
        created = mem.get('created', 'unknown')
        try:
            days = (datetime.now() - datetime.fromisoformat(created)).days
        except Exception:
            days = 0
        if score < 0.3:
            stale.append({**mem, "age_days": days, "level": "expired", "score": score})
        elif score < 0.5:
            stale.append({**mem, "age_days": days, "level": "stale", "score": score})
    return stale

def distill_memories(memories, dry_run=False):
    """Group memories by theme, distill 3+ into a principle."""
    groups = defaultdict(list)
    for mem in memories:
        theme = find_theme(mem)
        groups[theme].append(mem)

    distilled = []
    for theme, group in groups.items():
        if len(group) < 3:
            continue

        # Extract common patterns
        descriptions = [m.get('description', '') for m in group]
        types = set(m.get('type', '') for m in group)
        domains = set(m.get('domain', '') for m in group)

        # Build distilled principle
        principle_title = f"Distilled: {theme} principles ({len(group)} sources)"
        principle_body = f"## Distilled from {len(group)} memories\n\n"
        principle_body += f"**Theme:** {theme}\n"
        principle_body += f"**Source types:** {', '.join(types)}\n"
        principle_body += f"**Domains:** {', '.join(domains)}\n\n"
        principle_body += "### Source Memories\n\n"
        for m in group:
            aid = m.get('atomic_id', '?')
            desc = m.get('description', 'No description')[:120]
            principle_body += f"- [{aid}] {desc}\n"
        principle_body += "\n### Extracted Principle\n\n"
        principle_body += f"_Auto-distilled from {len(group)} related memories. Review and refine._\n"

        atomic_id = f"dist-{datetime.now().strftime('%Y%m%d')}-{hashlib.sha256(theme.encode()).hexdigest()[:6]}"
        filename = f"{atomic_id}-{theme}.md"

        if not dry_run:
            DISTILLED_DIR.mkdir(parents=True, exist_ok=True)
            content = f"""---
name: distilled-{theme}
description: "{principle_title}"
metadata:
  node_type: memory
  hierarchy: distilled
  node_path: distilled/{filename}
  type: insight
  domain: {theme}
  scope: global
  condition: when {theme}-related decisions are needed
  confidence: medium
  atomic_id: {atomic_id}
  created: {datetime.now().strftime('%Y-%m-%d')}
  updated: {datetime.now().strftime('%Y-%m-%d')}
  originSessionId: consolidator
  source_count: {len(group)}
  source_ids: [{', '.join(m.get('atomic_id', '?') for m in group)}]
---

{principle_body}
"""
            (DISTILLED_DIR / filename).write_text(content, encoding='utf-8')

        distilled.append({
            "theme": theme,
            "source_count": len(group),
            "atomic_id": atomic_id,
            "sources": [m.get('atomic_id', '?') for m in group],
        })

    return distilled

def archive_expired(memories, dry_run=False):
    """Archive expired memories (score < 0.3)."""
    archived = []
    for mem in memories:
        score = score_memory(mem)
        if score < 0.3:
            if not dry_run:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                src = Path(mem['_file'])
                if src.exists():
                    dst = ARCHIVE_DIR / src.name
                    src.rename(dst)
            archived.append({
                "id": mem.get('atomic_id', '?'),
                "file": mem.get('_rel', '?'),
                "score": score,
                "age_days": (datetime.now() - datetime.fromisoformat(mem.get('created', datetime.now().isoformat()))).days,
            })
    return archived

def prune_index(memories, dry_run=False):
    """Check and prune MEMORY.md."""
    if not MEMORY_INDEX.exists():
        return {"exists": False}

    content = MEMORY_INDEX.read_text(encoding='utf-8')
    lines_count = content.count('\n') + 1
    size_kb = len(content.encode('utf-8')) / 1024

    issues = []
    if lines_count > MAX_LINES:
        issues.append(f"lines: {lines_count} > {MAX_LINES}")
    if size_kb > MAX_SIZE_KB:
        issues.append(f"size: {size_kb:.1f}KB > {MAX_SIZE_KB}KB")

    # Count blank lines
    blank_lines = sum(1 for line in content.split('\n') if not line.strip())
    if blank_lines > 10:
        issues.append(f"blank lines: {blank_lines}")

    # Remove blank line runs
    if not dry_run and blank_lines > 10:
        cleaned = re.sub(r'\n{3,}', '\n\n', content)
        MEMORY_INDEX.write_text(cleaned, encoding='utf-8')

    return {
        "exists": True,
        "lines": lines_count,
        "size_kb": round(size_kb, 1),
        "blank_lines": blank_lines,
        "issues": issues,
    }

def rebuild_index(memories, dry_run=False):
    """Rebuild MEMORY.md index from current memory files."""
    by_hierarchy = defaultdict(list)
    for mem in memories:
        hier = mem.get('hierarchy', 'leaf')
        by_hierarchy[hier].append(mem)

    now = datetime.now()
    total = len(memories)

    lines = ["# Memory", ""]
    lines.append("> 樹狀記憶索引。root -> branch -> leaf -> distilled。")
    lines.append(f"> 總條數：{total} / 上限 50。最後更新：{now.strftime('%Y-%m-%d')}。")
    lines.append("")
    lines.append("## Scoring")
    lines.append("Every memory carries a confidence score **[0.0 - 1.0]** recalculated each session:")
    lines.append("")
    lines.append("| Factor | Rule |")
    lines.append("|---|---|")
    lines.append("| Base decay | e^(-days_since_creation / 30) (Ebbinghaus, 30-day half-life) |")
    lines.append("| Access boost | min(access_count * 0.05, 0.3) |")
    lines.append("| Recency boost | +0.15 if accessed under 7 days ago, +0.10 if under 30 days |")
    lines.append("| Success boost | +0.20 if memory was applied successfully (total capped at 1.0) |")
    lines.append("| Accelerated decay | x0.5 if unaccessed for 60+ days |")
    lines.append("")
    lines.append("Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3")

    section_config = [
        ("Root (Core Invariants)", "root", "核心不變量。永久保留。上限 10 條。"),
        ("Branch (Active Topics)", "branch", "活躍主題。上限 20 條。"),
        ("Leaf (Specific Facts)", "leaf", "具體事實、參考、坑記錄。上限 30 條。"),
        ("Distilled (Merged Memories)", "distilled", "合併記憶。自動生成。上限 15 條。"),
    ]

    for title, hier, desc in section_config:
        lines.append(f"## {title}")
        lines.append(f"> {desc}")
        lines.append("")
        group = by_hierarchy.get(hier, [])
        if group:
            for mem in group:
                aid = mem.get('atomic_id', '?')
                rel = mem.get('_rel', '?')
                desc_text = mem.get('description', 'No description')[:80]
                score = score_memory(mem)
                tag = "fresh" if score >= 0.8 else "aging" if score >= 0.5 else "stale" if score >= 0.3 else "expired"
                lines.append(f"- [{aid}]({rel}) — {desc_text} [{score:.2f} {tag}]")
        else:
            lines.append("(暫無)")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("## Score Formula")
    lines.append("```")
    lines.append("score = min(1.0, e^(-days/30) + min(access * 0.05, 0.3) + recency + success)")
    lines.append("recency = days_since_access lessThan 7 ? 0.15 : lessThan 30 ? 0.10 : 0")
    lines.append("success = applied_successfully ? 0.20 : 0")
    lines.append("if days_since_access >= 60: score = score * 0.5")
    lines.append("```")
    lines.append("")
    lines.append("Tags: [fresh] >= 0.8 / [aging] >= 0.5 / [stale] >= 0.3 / [expired] under 0.3")

    if not dry_run:
        MEMORY_INDEX.write_text('\n'.join(lines), encoding='utf-8')

    return {"lines": len(lines), "total": total}

def main():
    use_json = "--json" in sys.argv
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv
    do_distill = "--distill" in sys.argv or force
    do_archive = "--archive" in sys.argv or force

    state = load_state()
    can_run, reason = should_run(state, force)

    if not can_run and not dry_run and not use_json:
        print(f"MEMORY-CONSOLIDATOR: skipped ({reason})")
        return

    if not acquire_lock():
        print("MEMORY-CONSOLIDATOR: locked (another consolidation in progress)")
        return

    try:
        # Phase 1: Orient
        memories = load_all_memories()

        # Phase 2: Gather
        duplicates = find_duplicates(memories)
        stale = find_stale(memories)
        health = prune_index(memories, dry_run=True)

        # Phase 3: Consolidate
        distilled = []
        archived = []

        if do_distill:
            distilled = distill_memories(memories, dry_run=dry_run)

        if do_archive:
            expired_only = [s for s in stale if s.get('level') == 'expired']
            archived = archive_expired(expired_only, dry_run=dry_run)

        # Phase 4: Rebuild index (reload to include new distilled/archived)
        index_result = None
        if not dry_run and (duplicates or distilled or archived or health.get('issues')):
            memories = load_all_memories()  # Reload after distillation
            index_result = rebuild_index(memories, dry_run=dry_run)

        state["last_run"] = datetime.now().isoformat()
        state["sessions_since"] = 0
        state["total_runs"] += 1
        state["distilled_count"] += len(distilled)
        state["archived_count"] += len(archived)

        if not dry_run:
            save_state(state)

        result = {
            "status": "dry_run" if dry_run else "consolidated",
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "total_memories": len(memories),
            "duplicates_found": len(duplicates),
            "duplicates": duplicates[:5],
            "stale_found": len(stale),
            "stale": [{"id": s.get('atomic_id', '?'), "age_days": s.get('age_days', 0), "level": s.get('level', '?')} for s in stale[:5]],
            "distilled": distilled,
            "archived": archived,
            "index_rebuilt": index_result is not None,
            "index_health": health,
        }

        if use_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"MEMORY-CONSOLIDATOR v2: {result['status']} — {reason}")
            print(f"  Memories: {len(memories)} | Duplicates: {len(duplicates)} | Stale: {len(stale)}")
            if distilled:
                print(f"  Distilled: {len(distilled)} new principles")
                for d in distilled:
                    print(f"    → {d['theme']}: {d['source_count']} sources → {d['atomic_id']}")
            if archived:
                print(f"  Archived: {len(archived)} expired memories")
            if health.get('issues'):
                print(f"  Index issues: {', '.join(health['issues'])}")

    finally:
        release_lock()

if __name__ == "__main__":
    main()
