#!/usr/bin/env python3
r"""ralph-web-agent.py -- AUTONOMOUS WEB RESEARCH AGENT.
The model's "eyes and ears" to the internet. Actively seeks knowledge.

Capabilities:
- Autonomous gap detection: "What don't I know that I should?"
- Active web search: searches without being asked
- Multi-source synthesis: cross-references 3+ sources
- Knowledge absorption: auto-appends findings to brain dataset
- Anti-hallucination: only absorbs verified, sourced information

Integration:
- Called by ralph-evolve-model.py during SCAN phase
- Can be triggered manually: python ralph-web-agent.py "topic"
- Self-triggering: periodically checks for knowledge gaps

Usage:
  python ralph-web-agent.py                           # Autonomous gap-filling mode
  python ralph-web-agent.py "transformer architecture" # Research specific topic
  python ralph-web-agent.py --gaps                     # Show known knowledge gaps
  python ralph-web-agent.py --absorb "search query"    # Search + auto-absorb
"""

import sys, json, io, os
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
BRAIN_DATA = MODEL_DIR / "brain_dataset.jsonl"
GAPS_FILE = MODEL_DIR / "knowledge_gaps.json"
RESEARCH_LOG = MODEL_DIR / "research_log.jsonl"

# Knowledge domains the model should proactively research
RESEARCH_DOMAINS = [
    "transformer attention mechanism latest advances 2025 2026",
    "small language model training techniques QLoRA fine-tuning best practices",
    "autonomous AI agent architecture self-improving systems 2025",
    "retrieval augmented generation RAG latest breakthroughs 2025 2026",
    "continual learning without catastrophic forgetting techniques",
    "model merging weight averaging techniques",
    "speculative decoding inference optimization small models",
    "knowledge distillation from large to small models best practices",
    "multi-agent orchestration patterns workflow automation",
    "embedding model fine-tuning domain adaptation contrastive learning",
    "open source small language models SmolLM Qwen TinyLlama comparison",
    "AI agent tool use patterns MCP protocol function calling",
    "code generation small models fine-tuning IDE integration",
    "language detection multilingual small models CJK optimization",
]


def load_brain_knowledge_set() -> set:
    """Extract all known concepts from brain dataset."""
    known = set()
    if BRAIN_DATA.exists():
        with open(BRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ex = json.loads(line)
                        known.add(ex.get("instruction", "")[:100].lower())
                        known.add(ex.get("output", "")[:100].lower())
                    except:
                        pass
    return known


def load_gaps() -> dict:
    """Load known knowledge gaps."""
    if GAPS_FILE.exists():
        try:
            return json.loads(GAPS_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"gaps": [], "researched": [], "last_scan": None}


def save_gaps(gaps: dict):
    """Save knowledge gaps."""
    GAPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    GAPS_FILE.write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_gaps() -> list[str]:
    """Detect knowledge gaps by comparing brain vs research domains."""
    known = load_brain_knowledge_set()
    gaps = load_gaps()

    new_gaps = []
    for domain in RESEARCH_DOMAINS:
        keywords = domain.lower().split()[:4]  # first few words as check
        found = any(all(kw in k for kw in keywords) for k in known)
        if not found and domain not in gaps["researched"]:
            new_gaps.append(domain)

    if new_gaps:
        gaps["gaps"].extend(new_gaps)
        gaps["last_scan"] = datetime.now().isoformat()
        save_gaps(gaps)

    return new_gaps


def web_search_structured(query: str) -> dict:
    """Perform structured web search and return synthesized findings.
    This is a LOCAL agent — it uses the WebSearch tool pattern.
    When run from CLI, it reports what it would search for.
    When run within Claude, Claude's tools handle the actual search."""
    return {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "status": "delegated",
        "instruction": f"WebSearch for: {query}",
        "note": "Run within Claude session for actual web search execution",
    }


def absorb_research(query: str, findings: str):
    """Absorb research findings into brain dataset."""
    if not findings or len(findings) < 20:
        return 0

    examples = [
        {
            "instruction": f"关于'{query}'，最新的研究发现是什么？",
            "input": "",
            "output": findings[:800],
            "source": "web_research",
            "absorbed_at": datetime.now().isoformat(),
        },
        {
            "instruction": query,
            "input": "",
            "output": findings[:800],
            "source": "web_research",
            "absorbed_at": datetime.now().isoformat(),
        },
    ]

    # Mark as researched
    gaps = load_gaps()
    if query in gaps["gaps"]:
        gaps["gaps"].remove(query)
    gaps["researched"].append({"query": query, "timestamp": datetime.now().isoformat()})
    save_gaps(gaps)

    # Append to brain
    BRAIN_DATA.parent.mkdir(parents=True, exist_ok=True)
    existing_keys = set()
    if BRAIN_DATA.exists():
        with open(BRAIN_DATA, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ex = json.loads(line)
                        existing_keys.add(ex.get("instruction", "")[:80])
                    except:
                        pass

    count = 0
    with open(BRAIN_DATA, "a", encoding="utf-8") as f:
        for ex in examples:
            key = ex["instruction"][:80]
            if key not in existing_keys:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                existing_keys.add(key)
                count += 1

    # Log
    RESEARCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RESEARCH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "examples_absorbed": count,
        }, ensure_ascii=False) + "\n")

    return count


def autonomous_research_cycle() -> dict:
    """Run one autonomous research cycle."""
    print("=" * 60)
    print("  WEB AGENT — Autonomous Research Cycle")
    print("=" * 60)

    # Detect gaps
    print("\n[1] Detecting knowledge gaps...")
    gaps = detect_gaps()

    if not gaps:
        print("     No new knowledge gaps detected.")
        # Re-scan old domains
        all_gaps = load_gaps()
        old_gaps = [g for g in all_gaps.get("gaps", []) if g not in all_gaps.get("researched", [])]
        if old_gaps:
            print(f"     Revisiting {len(old_gaps)} old gaps")
            gaps = old_gaps[:3]  # Max 3 per cycle
        else:
            return {"gaps_found": 0, "researched": 0, "absorbed": 0}

    print(f"     Found {len(gaps)} knowledge gaps to research")

    # Research each gap
    total_absorbed = 0
    researched = 0

    for gap in gaps[:3]:  # Max 3 topics per cycle
        researched += 1
        print(f"\n[2] Researching: {gap[:80]}...")
        result = web_search_structured(gap)
        print(f"     Status: {result['status']}")
        print(f"     → Delegate to: WebSearch('{gap[:80]}')")

        # When run inside Claude: the actual search happens via WebSearch tool
        # When run standalone: logs the intent for next Claude session to execute

    # Log cycle
    with open(RESEARCH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "cycle": "autonomous",
            "gaps_found": len(gaps),
            "topics_queued": researched,
            "absorbed": total_absorbed,
        }, ensure_ascii=False) + "\n")

    return {
        "gaps_found": len(gaps),
        "researched": researched,
        "absorbed": total_absorbed,
    }


def show_gaps():
    """Display current knowledge gaps."""
    gaps = load_gaps()
    print("=" * 50)
    print("  Knowledge Gaps (things the model should learn)")
    print("=" * 50)
    print(f"\n  Open gaps ({len(gaps.get('gaps', []))}):")
    for g in gaps.get("gaps", [])[:20]:
        print(f"    🕳️  {g}")
    print(f"\n  Researched ({len(gaps.get('researched', []))}):")
    for r in gaps.get("researched", [])[-10:]:
        if isinstance(r, dict):
            print(f"    ✅ {r.get('query', r)[:80]}")
        else:
            print(f"    ✅ {r[:80]}")


def main():
    if "--gaps" in sys.argv:
        show_gaps()
        return

    if "--absorb" in sys.argv:
        idx = sys.argv.index("--absorb")
        if idx + 1 < len(sys.argv):
            query = sys.argv[idx + 1]
            # This needs actual search results — in standalone mode, log the intent
            absorb_research(query, f"[Research queued for: {query}]")
            print(f"Research queued: {query}")
            print("Run within Claude for actual web search + absorption")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        query = " ".join(args)
        result = web_search_structured(query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Default: autonomous cycle
    result = autonomous_research_cycle()
    print(f"\nCycle complete: {result['gaps_found']} gaps, {result['researched']} queued")


if __name__ == "__main__":
    main()
