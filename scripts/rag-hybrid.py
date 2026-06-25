#!/usr/bin/env python3
"""rag-hybrid — EnsembleRetriever pattern: parallel keyword + semantic search with RRF fusion.
LangChain-inspired: runs Grep (keyword) and KG (semantic) in parallel, then fuses results.

Usage:
  python rag-hybrid.py "encoding bug"              # Hybrid search
  python rag-hybrid.py --json "memory search"       # JSON output
  python rag-hybrid.py --k 5 "rule"                # Top-5 results
  python rag-hybrid.py --bench                      # Run benchmark on known queries
"""

import sys, json, io, subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MEMORY_DIR = HOME / "projects" / "C--Users-z1439--claude" / "memory"
RULES_DIR = HOME / ".claude" / "rules"

# ═══════════════════════════════════════════
# Sparse Retriever: Keyword Grep
# ═══════════════════════════════════════════

def keyword_search(query: str, k: int = 10) -> list[tuple[str, float]]:
    """BM25-style keyword search across memory and rule files."""
    results = []
    query_terms = query.lower().split()
    search_dirs = [MEMORY_DIR, RULES_DIR]

    for directory in search_dirs:
        if not directory.exists():
            continue
        for f in directory.rglob("*.md"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Simple TF scoring
            content_lower = content.lower()
            score = 0.0

            # Exact phrase match (highest weight)
            if query.lower() in content_lower:
                score += 3.0

            # Individual term matches
            for term in query_terms:
                count = content_lower.count(term)
                if count > 0:
                    # TF component with length normalization
                    doc_len = max(len(content_lower), 1)
                    tf = count / (doc_len / 100)  # per 100 chars
                    score += min(tf, 2.0)  # cap per-term contribution

            # Title/description boost
            if f.stem.lower() in query.lower() or query.lower() in f.stem.lower():
                score += 2.0

            if score > 0:
                results.append((str(f.relative_to(HOME)), score))

    # Normalize scores to [0, 1]
    if results:
        max_score = max(s for _, s in results)
        results = [(path, s / max_score) for path, s in results]

    results.sort(key=lambda x: -x[1])
    return results[:k]


# ═══════════════════════════════════════════
# Dense Retriever: Semantic via memory-search.py
# ═══════════════════════════════════════════

def semantic_search(query: str, k: int = 10) -> list[tuple[str, float]]:
    """Semantic search via knowledge graph (memory-search.py)."""
    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "memory-search.py"), "--json", query],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        results = []
        for item in data.get("results", [])[:k]:
            path = item.get("file", item.get("id", "unknown"))
            score = item.get("score", 0.5)
            results.append((path, score))
        return results
    except Exception:
        return []


# ═══════════════════════════════════════════
# Fusion: Reciprocal Rank Fusion (RRF)
# ═══════════════════════════════════════════

def reciprocal_rank_fusion(
    keyword_results: list[tuple[str, float]],
    semantic_results: list[tuple[str, float]],
    k_rrf: int = 60,
    weights: tuple[float, float] = (0.5, 0.5),
) -> list[tuple[str, float]]:
    """Fuse two ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(weight_i / (k + rank_i)) for each retriever i.
    k=60 is the standard; tune lower (20-30) for Chinese language.
    """
    scores = defaultdict(float)

    for rank, (path, _) in enumerate(keyword_results, start=1):
        scores[path] += weights[0] / (k_rrf + rank)

    for rank, (path, _) in enumerate(semantic_results, start=1):
        scores[path] += weights[1] / (k_rrf + rank)

    # Sort by fused score descending
    fused = sorted(scores.items(), key=lambda x: -x[1])
    return fused


def hybrid_search(query: str, k: int = 10) -> list[dict]:
    """Full hybrid search pipeline."""
    # Run both retrievers
    keyword_results = keyword_search(query, k=k * 2)  # oversample
    semantic_results = semantic_search(query, k=k * 2)

    # Fuse
    fused = reciprocal_rank_fusion(keyword_results, semantic_results)

    # Build result objects
    results = []
    for path, score in fused[:k]:
        results.append({
            "path": path,
            "score": round(score, 4),
            "source": (
                "both" if path in dict(keyword_results) and path in dict(semantic_results)
                else "keyword" if path in dict(keyword_results)
                else "semantic"
            ),
        })

    return results


# ═══════════════════════════════════════════
# Benchmark
# ═══════════════════════════════════════════

BENCHMARK_QUERIES = [
    ("进化规则", ["evolution.md", "evolve"]),
    ("错误处理", ["errors.md", "error"]),
    ("安全边界", ["security.md", "security"]),
    ("并行执行", ["parallel.md", "parallel"]),
    ("记忆系统", ["memory", "MEMORY.md"]),
]


def run_benchmark() -> dict:
    """Evaluate hybrid search against known queries."""
    total = 0
    found = 0

    for query, expected_terms in BENCHMARK_QUERIES:
        results = hybrid_search(query, k=5)
        total += 1

        # Check if any expected term appears in results
        result_text = json.dumps(results).lower()
        if any(term.lower() in result_text for term in expected_terms):
            found += 1

    return {
        "total_queries": total,
        "found": found,
        "recall": round(found / max(total, 1), 2),
    }


def main():
    if "--bench" in sys.argv:
        bench = run_benchmark()
        print(f"Hybrid Search Benchmark: {bench['found']}/{bench['total_queries']} (recall={bench['recall']:.0%})")
        sys.exit(0 if bench["recall"] >= 0.6 else 1)

    use_json = "--json" in sys.argv
    k = 10

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Parse --k flag
    for i, a in enumerate(sys.argv):
        if a == "--k" and i + 1 < len(sys.argv):
            k = int(sys.argv[i + 1])

    if args:
        query = " ".join(args)
    elif not sys.stdin.isatty():
        query = sys.stdin.read().strip()
    else:
        print(__doc__)
        sys.exit(0)

    if not query:
        print(json.dumps({"results": [], "query": ""}))
        sys.exit(0)

    results = hybrid_search(query, k=k)

    if use_json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "results": results,
            "total": len(results),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"HYBRID SEARCH: '{query}' → {len(results)} results")
        for r in results:
            icon = "🔀" if r["source"] == "both" else "🔤" if r["source"] == "keyword" else "🧠"
            print(f"  {icon} [{r['source']:8s}] {r['path']} (score={r['score']:.4f})")


if __name__ == "__main__":
    main()
