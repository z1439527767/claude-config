#!/usr/bin/env python3
"""rag-evaluate — retrieval quality evaluator (RAGAS-inspired).
Measures: recall, precision, MRR, and retrieval confidence.
Integrates with self-bench.py for objective capability tracking.

Usage:
  python rag-evaluate.py                    # Evaluate all retrievers
  python rag-evaluate.py --json             # Machine-readable
  python rag-evaluate.py --query "error"    # Single query evaluation
"""

import sys, json, io, subprocess, time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent

# ═══════════════════════════════════════════
# Test Queries + Expected Results (Golden Set)
# ═══════════════════════════════════════════

GOLDEN_QUERIES = [
    {
        "query": "错误处理",
        "expected_files": ["errors.md", "error"],
        "expected_terms": ["RETRY", "FIX", "ROLLBACK", "ESCALATE"],
    },
    {
        "query": "并行执行规则",
        "expected_files": ["parallel.md", "parallel"],
        "expected_terms": ["并行", "parallel", "互不依赖"],
    },
    {
        "query": "安全边界",
        "expected_files": ["security.md", "security"],
        "expected_terms": ["deny-first", "不可信", "injection"],
    },
    {
        "query": "记忆系统",
        "expected_files": ["memory", "MEMORY.md"],
        "expected_terms": ["Ebbinghaus", "遗忘", "衰减", "scoring"],
    },
    {
        "query": "进化策略",
        "expected_files": ["evolution.md", "evolve"],
        "expected_terms": ["balanced", "innovate", "harden", "gate"],
    },
    {
        "query": "上下文管理",
        "expected_files": ["context.md", "context"],
        "expected_terms": ["60%", "安全线", "剪枝", "Rubric"],
    },
    {
        "query": "代码修改流程",
        "expected_files": ["code-change.md", "code"],
        "expected_terms": ["读过再改", "改过必验", "Edit"],
    },
    {
        "query": "问题解决",
        "expected_files": ["problem-solving.md", "problem"],
        "expected_terms": ["OODA", "Observe", "Orient", "Decide", "Act"],
    },
]


def run_keyword_retrieval(query: str) -> list[str]:
    """Run keyword-only retrieval (via rag-hybrid keyword component)."""
    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "rag-hybrid.py"), "--json", "--k", "10", query],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        data = json.loads(result.stdout)
        return [r["path"] for r in data.get("results", []) if r.get("source") == "keyword"]
    except Exception:
        return []


def run_semantic_retrieval(query: str) -> list[str]:
    """Run semantic-only retrieval (via rag-hybrid semantic component)."""
    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "rag-hybrid.py"), "--json", "--k", "10", query],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        data = json.loads(result.stdout)
        return [r["path"] for r in data.get("results", []) if r.get("source") == "semantic"]
    except Exception:
        return []


def run_hybrid_retrieval(query: str) -> list[str]:
    """Run full hybrid retrieval."""
    try:
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "rag-hybrid.py"), "--json", "--k", "10", query],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        data = json.loads(result.stdout)
        return [r["path"] for r in data.get("results", [])]
    except Exception:
        return []


def run_rewritten_retrieval(query: str) -> list[str]:
    """Retrieval with query rewriting."""
    try:
        # Get rewritten queries
        result = subprocess.run(
            ["python", str(HOME / "scripts" / "rag-rewrite.py"), "--json", query],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        variants = json.loads(result.stdout).get("variants", [query])

        # Run hybrid search for each variant and merge
        all_paths = set()
        for v in variants[:3]:
            paths = run_hybrid_retrieval(v)
            all_paths.update(paths)
        return list(all_paths)
    except Exception:
        return run_hybrid_retrieval(query)


def compute_recall_at_k(retrieved: list[str], expected_files: list[str], k: int = 5) -> float:
    """Recall@k: fraction of expected files found in top-k results."""
    top_k = retrieved[:k]
    found = sum(1 for ef in expected_files if any(ef.lower() in r.lower() for r in top_k))
    return found / max(len(expected_files), 1)


def compute_mrr(retrieved: list[str], expected_files: list[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant result."""
    for rank, path in enumerate(retrieved, start=1):
        if any(ef.lower() in path.lower() for ef in expected_files):
            return 1.0 / rank
    return 0.0


def compute_retrieval_confidence(retrieved: list[str], expected_terms: list[str]) -> float:
    """Check if retrieved content contains expected key terms."""
    if not retrieved:
        return 0.0

    matches = 0
    for path in retrieved[:5]:
        full_path = HOME / path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore").lower()
                for term in expected_terms:
                    if term.lower() in content:
                        matches += 1
                        break
            except Exception:
                pass

    return matches / min(len(retrieved[:5]), 5)


def evaluate_retriever(name: str, retriever_fn, queries: list[dict]) -> dict:
    """Evaluate a single retriever across all golden queries."""
    recalls = []
    mrrs = []
    confidences = []
    timings = []

    for q in queries:
        start = time.time()
        results = retriever_fn(q["query"])
        elapsed = time.time() - start

        recall = compute_recall_at_k(results, q["expected_files"])
        mrr = compute_mrr(results, q["expected_files"])
        confidence = compute_retrieval_confidence(results, q["expected_terms"])

        recalls.append(recall)
        mrrs.append(mrr)
        confidences.append(confidence)
        timings.append(elapsed)

    return {
        "name": name,
        "recall@5": round(sum(recalls) / len(recalls), 3),
        "MRR": round(sum(mrrs) / len(mrrs), 3),
        "confidence": round(sum(confidences) / len(confidences), 3),
        "avg_latency_ms": round((sum(timings) / len(timings)) * 1000),
        "queries_evaluated": len(queries),
        "combined_score": round(
            (sum(recalls) / len(recalls)) * 0.4 +
            (sum(mrrs) / len(mrrs)) * 0.3 +
            (sum(confidences) / len(confidences)) * 0.3, 3
        ),
    }


def main():
    use_json = "--json" in sys.argv
    single_query = None

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        single_query = " ".join(args)

    queries = GOLDEN_QUERIES
    if single_query:
        queries = [{
            "query": single_query,
            "expected_files": [],
            "expected_terms": [],
        }]

    retrievers = [
        ("keyword-only", run_keyword_retrieval),
        ("semantic-only", run_semantic_retrieval),
        ("hybrid", run_hybrid_retrieval),
        ("hybrid+rewrite", run_rewritten_retrieval),
    ]

    results = []
    for name, fn in retrievers:
        try:
            result = evaluate_retriever(name, fn, queries)
            results.append(result)
        except Exception as e:
            results.append({"name": name, "error": str(e)})

    if use_json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "retrievers": results,
            "best": max(results, key=lambda r: r.get("combined_score", 0)) if results else None,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════════╗")
        print(f"║  Retrieval Quality Evaluation (RAGAS)    ║")
        print(f"╠══════════════════════════════════════════╣")
        print(f"║  {len(queries)} golden queries × 4 retrievers          ║")
        print(f"╚══════════════════════════════════════════╝")
        print()

        for r in results:
            if "error" in r:
                print(f"  🔴 {r['name']}: ERROR — {r['error']}")
                continue
            score = r["combined_score"]
            icon = "✅" if score >= 0.7 else "⚠️" if score >= 0.4 else "🔴"
            print(f"  {icon} {r['name']:20s}  Recall@5={r['recall@5']:.2f}  MRR={r['MRR']:.2f}  "
                  f"Conf={r['confidence']:.2f}  Lat={r['avg_latency_ms']}ms  Score={score:.2f}")


if __name__ == "__main__":
    main()
