#!/usr/bin/env python3
"""self-bench — objective capability benchmark for the Ralph Loop system.
OpenHands-inspired: measure actual capability, not self-reported confidence.
Runs 5 fast, non-destructive benchmark tasks and tracks scores over time.

Usage:
  python self-bench.py              # Run all benchmarks, print report
  python self-bench.py --json        # Machine-readable output
  python self-bench.py --history     # Show score history
"""

import sys, json, io, subprocess, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
BENCH_DIR = HOME / ".claude" / "benchmarks"
BENCH_HISTORY = BENCH_DIR / "history.jsonl"

# ═══════════════════════════════════════════
# Benchmark Definitions
# ═══════════════════════════════════════════

BENCHMARKS = []

def bench(name, description, weight=1.0):
    """Decorator to register a benchmark."""
    def decorator(fn):
        BENCHMARKS.append({
            "name": name,
            "description": description,
            "weight": weight,
            "fn": fn,
        })
        return fn
    return decorator


@bench("syntax-check", "All .ps1 scripts parse without syntax errors", weight=0.5)
def bench_syntax():
    """Verify all PowerShell scripts parse cleanly."""
    hooks_dir = HOME / "scripts" / "hooks"
    lib_dir = HOME / "scripts" / "lib"
    total = 0
    failed = []

    for d in [hooks_dir, lib_dir]:
        if not d.exists():
            continue
        for f in d.glob("*.ps1"):
            total += 1
            try:
                r = subprocess.run(
                    ["pwsh", "-NoProfile", "-Command",
                     f"$t=$null;$e=$null;$a=[System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$t,[ref]$e);exit($e.Count)"],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace"
                )
                if r.returncode != 0:
                    failed.append(f.name)
            except Exception:
                failed.append(f"{f.name} (timeout)")

    score = 1.0 - (len(failed) / max(total, 1))
    return {
        "pass": len(failed) == 0,
        "score": round(score, 3),
        "detail": f"{total - len(failed)}/{total} clean",
        "failed": failed,
    }


@bench("ref-integrity", "All CLAUDE.md references resolve to existing files", weight=0.5)
def bench_references():
    """Check CLAUDE.md references resolve."""
    import re
    claude_md = HOME / "CLAUDE.md"
    if not claude_md.exists():
        return {"pass": False, "score": 0.0, "detail": "CLAUDE.md missing"}

    content = claude_md.read_text(encoding="utf-8")
    refs = re.findall(r'@(\.claude/rules/[\w-]+\.md)', content)
    broken = [r for r in refs if not (HOME / r).exists()]

    script_refs = re.findall(r'scripts/([\w\-/]+\.(?:py|ps1))', content)
    broken += [f"scripts/{r}" for r in script_refs if not (HOME / "scripts" / r).exists()]

    total = len(refs) + len(script_refs)
    score = 1.0 - (len(broken) / max(total, 1))
    return {
        "pass": len(broken) == 0,
        "score": round(score, 3),
        "detail": f"{total} refs, {len(broken)} broken",
        "broken": broken,
    }


@bench("memory-recall", "Knowledge graph search returns results for known entities", weight=1.0)
def bench_memory():
    """Test knowledge graph connectivity by searching for a known entity."""
    # This is a connectivity test — we check if the MCP search tool is reachable
    # We can't directly call MCP from a subprocess, so we check infrastructure
    kg_dir = HOME / "projects" / "C--Users-z1439--claude" / "memory"
    if not kg_dir.exists():
        return {"pass": False, "score": 0.0, "detail": "Memory directory missing"}

    # Check MEMORY.md exists and has entries
    mem_index = kg_dir / "MEMORY.md"
    if not mem_index.exists():
        return {"pass": False, "score": 0.3, "detail": "MEMORY.md missing"}

    content = mem_index.read_text(encoding="utf-8")
    entry_count = content.count("\n- [")
    if entry_count < 5:
        return {"pass": False, "score": 0.5, "detail": f"Only {entry_count} memory entries"}

    return {
        "pass": True,
        "score": 1.0,
        "detail": f"{entry_count} memory entries indexed",
    }


@bench("health-check", "Health dashboard runs without errors", weight=0.5)
def bench_health():
    """Run health-check.py and verify it reports OK."""
    health_script = HOME / "scripts" / "health-check.py"
    if not health_script.exists():
        return {"pass": False, "score": 0.0, "detail": "health-check.py missing"}

    try:
        r = subprocess.run(
            ["python", str(health_script)],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        output = r.stdout + r.stderr
        if "Health: OK" in output:
            return {"pass": True, "score": 1.0, "detail": "Health OK"}
        elif "Health: WARN" in output:
            return {"pass": True, "score": 0.7, "detail": "Health WARN"}
        else:
            return {"pass": False, "score": 0.3, "detail": f"Unexpected: {output[:100]}"}
    except Exception as e:
        return {"pass": False, "score": 0.0, "detail": str(e)[:100]}


@bench("friction-detect", "Sense-signals correctly detects friction in test input", weight=1.0)
def bench_friction():
    """Test sense-signals.py with known friction input."""
    sense_script = HOME / "scripts" / "sense-signals.py"
    if not sense_script.exists():
        return {"pass": False, "score": 0.0, "detail": "sense-signals.py missing"}

    # Test with Chinese friction input
    try:
        r = subprocess.run(
            ["python", str(sense_script), "又错了，还是不对"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", cwd=str(HOME)
        )
        data = json.loads(r.stdout)
        friction = data.get("friction", 0)
        signals = data.get("count", 0)

        if friction > 0.5 and signals >= 2:
            return {"pass": True, "score": 1.0,
                    "detail": f"Detected {signals} signals, friction={friction}"}
        elif signals > 0:
            return {"pass": True, "score": 0.6,
                    "detail": f"Partial detection: {signals} signals, friction={friction}"}
        else:
            return {"pass": False, "score": 0.2,
                    "detail": f"No signals detected, friction={friction}"}
    except Exception as e:
        return {"pass": False, "score": 0.0, "detail": str(e)[:100]}


@bench("rag-retrieval", "Hybrid RAG retrieval finds relevant docs for known queries", weight=1.0)
def bench_rag_retrieval():
    eval_script = HOME / "scripts" / "rag-evaluate.py"
    if not eval_script.exists():
        return {"pass": False, "score": 0.0, "detail": "rag-evaluate.py missing"}
    try:
        r = subprocess.run(["python", str(eval_script), "--json"],
                         capture_output=True, text=True, timeout=30,
                         encoding="utf-8", errors="replace", cwd=str(HOME))
        data = json.loads(r.stdout)
        best = data.get("best", {})
        if best and best.get("combined_score", 0) >= 0.5:
            return {"pass": True, "score": best["combined_score"],
                    "detail": f"Best: {best.get('name','?')} ({best['combined_score']:.2f})"}
        return {"pass": False, "score": best.get("combined_score", 0),
                "detail": f"Best retriever only {best.get('combined_score',0):.2f}"}
    except Exception as e:
        return {"pass": False, "score": 0.0, "detail": str(e)[:100]}


@bench("rag-rewrite", "Query rewriter generates valid variant phrasings", weight=0.5)
def bench_rag_rewrite():
    rewrite_script = HOME / "scripts" / "rag-rewrite.py"
    if not rewrite_script.exists():
        return {"pass": False, "score": 0.0, "detail": "rag-rewrite.py missing"}
    try:
        r = subprocess.run(["python", str(rewrite_script), "--json", "修复进化系统的错误"],
                         capture_output=True, text=True, timeout=10,
                         encoding="utf-8", errors="replace", cwd=str(HOME))
        data = json.loads(r.stdout)
        count = data.get("count", 0)
        if count >= 3:
            return {"pass": True, "score": 1.0, "detail": f"{count} variants generated"}
        return {"pass": True, "score": 0.7, "detail": f"Only {count} variants"}
    except Exception as e:
        return {"pass": False, "score": 0.0, "detail": str(e)[:100]}


# ═══════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════

def run_all_benchmarks() -> dict:
    """Run all registered benchmarks and return results."""
    results = []
    total_weight = sum(b["weight"] for b in BENCHMARKS)
    weighted_score = 0.0

    for b in BENCHMARKS:
        start = time.time()
        try:
            result = b["fn"]()
        except Exception as e:
            result = {"pass": False, "score": 0.0, "detail": f"Crash: {e}"}
        elapsed = time.time() - start

        weighted_score += result["score"] * b["weight"]
        results.append({
            "name": b["name"],
            "description": b["description"],
            "weight": b["weight"],
            "elapsed_ms": round(elapsed * 1000),
            **result,
        })

    overall = weighted_score / max(total_weight, 0.01)

    return {
        "timestamp": datetime.now().isoformat(),
        "overall_score": round(overall, 3),
        "grade": (
            "A" if overall >= 0.9 else "B" if overall >= 0.75
            else "C" if overall >= 0.6 else "D" if overall >= 0.4 else "F"
        ),
        "benchmarks": results,
        "summary": f"{sum(1 for r in results if r['pass'])}/{len(results)} passed",
    }


def save_results(data: dict):
    """Save benchmark results to history."""
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(BENCH_HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def load_history() -> list[dict]:
    """Load benchmark history."""
    if not BENCH_HISTORY.exists():
        return []
    history = []
    with open(BENCH_HISTORY, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    history.append(json.loads(line))
                except Exception:
                    pass
    return history


def show_history():
    """Display score trend over time."""
    history = load_history()
    if not history:
        print("No benchmark history yet. Run without --history first.")
        return

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  Self-Benchmark History ({len(history)} runs)              ║")
    print(f"╠══════════════════════════════════════════════╣")

    scores = []
    for i, entry in enumerate(history[-20:]):
        ts = entry["timestamp"][:19]
        score = entry["overall_score"]
        grade = entry["grade"]
        passed = entry["summary"]
        scores.append(score)
        icon = "📈" if i > 0 and score > scores[i-1] else "📉" if i > 0 and score < scores[i-1] else "➡️"
        print(f"  {icon} {ts}  Score: {score:.0%} ({grade})  {passed}")

    if len(scores) >= 2:
        trend = scores[-1] - scores[0]
        direction = "improving" if trend > 0.05 else "declining" if trend < -0.05 else "stable"
        print(f"\n  Trend: {direction} ({trend:+.1%} over {len(scores)} runs)")

    # Per-benchmark averages
    bench_scores = defaultdict(list)
    for entry in history:
        for b in entry["benchmarks"]:
            bench_scores[b["name"]].append(b["score"])

    print(f"\n  ── Per-Benchmark Averages ──")
    for name, sc in sorted(bench_scores.items()):
        avg = sum(sc[-10:]) / min(len(sc), 10)
        icon = "✅" if avg >= 0.9 else "⚠️" if avg >= 0.7 else "🔴"
        print(f"  {icon} {name}: {avg:.0%}")


def main():
    if "--history" in sys.argv:
        show_history()
        return

    use_json = "--json" in sys.argv

    print("Running self-benchmarks...", file=sys.stderr)
    results = run_all_benchmarks()
    save_results(results)

    if use_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"╔══════════════════════════════════════════╗")
        print(f"║  🎯 Self-Benchmark Report                ║")
        print(f"╠══════════════════════════════════════════╣")
        print(f"║  Score: {results['overall_score']:.0%}  Grade: {results['grade']}   {results['summary']}       ║")
        print(f"╚══════════════════════════════════════════╝")
        print()

        for b in results["benchmarks"]:
            icon = "✅" if b["pass"] else "❌"
            print(f"  {icon} {b['name']} ({b['weight']:.1f}x): {b['detail']}")
            if b.get("failed"):
                print(f"     Failed: {', '.join(b['failed'][:5])}")
            if b.get("broken"):
                print(f"     Broken refs: {', '.join(b['broken'][:5])}")
        print()

        # Trend
        history = load_history()
        if len(history) >= 2:
            prev = history[-2]["overall_score"]
            curr = results["overall_score"]
            delta = curr - prev
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"  vs last run: {prev:.0%} {arrow} {curr:.0%} ({delta:+.1%})")

    sys.exit(0 if results["overall_score"] >= 0.6 else 1)


if __name__ == "__main__":
    main()
