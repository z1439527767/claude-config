#!/usr/bin/env python3
r"""distill-brain.py -- extract ALL Ralph Loop knowledge into a training corpus.
Output: structured brain dataset for fine-tuning a small language model.

Sources distilled:
- 22 rules (tools, errors, security, thinking, etc.)
- 18 memories (behavior, preferences, lessons)
- 30+ scripts (tool APIs, workflows)
- Evolution patterns (L1-L5 strategies)
- Hook system (30 hooks, their triggers and purposes)
- MCP tools (memory, context7, sequential-thinking, etc.)
- RAG pipeline (rewrite, hybrid, evaluate)
- OpenHands patterns (event sourcing, plugin protocol, SWE-bench)
- LangChain patterns (MultiQuery, Ensemble, RAGAS, CRAG)

Output: MODEL_DIR/brain_dataset.jsonl -- line-delimited JSON for training
"""

import sys, json, io, re, os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HOME = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("RALPH_MODEL_DIR", r"C:\Users\z1439\OneDrive\Desktop\模型"))
RULES_DIR = HOME / ".claude" / "rules"
MEMORY_DIR = HOME / "projects" / "C--Users-z1439--claude" / "memory"
SCRIPTS_DIR = HOME / "scripts"
HOOKS_DIR = SCRIPTS_DIR / "hooks"
LIB_DIR = SCRIPTS_DIR / "lib"
CLAUDE_MD = HOME / "CLAUDE.md"
SETTINGS_FILE = HOME / "settings.json"

# ═══════════════════════════════════════════
# Knowledge Collectors
# ═══════════════════════════════════════════

def collect_rules() -> list[dict]:
    """Extract all rules as knowledge entries."""
    entries = []
    for f in sorted(RULES_DIR.rglob("*.md")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        # Extract title from first heading
        title_m = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else f.stem

        # Extract key points (bullet lists, bold text, code blocks)
        bullets = re.findall(r'^[-*]\s+(.+)$', content, re.MULTILINE)
        bold_items = re.findall(r'\*\*(.+?)\*\*', content)

        entries.append({
            "type": "rule",
            "source": f"rules/{f.name}",
            "title": title,
            "key_points": bullets[:15],
            "keywords": bold_items[:10],
            "content_preview": content[:800],
        })
    return entries

def collect_memories() -> list[dict]:
    """Extract all memories."""
    entries = []
    for f in sorted(MEMORY_DIR.rglob("*.md")):
        if f.name == "MEMORY.md":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        # Parse frontmatter
        meta = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                for line in content[3:end].split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip().strip('"')
        body = content[content.find("---", 3)+3:].strip() if "---" in content[3:] else content

        entries.append({
            "type": "memory",
            "source": f"memory/{f.relative_to(MEMORY_DIR)}",
            "meta": meta,
            "body": body[:600],
        })
    return entries

def collect_scripts() -> list[dict]:
    """Extract tool/script knowledge."""
    entries = []
    for f in sorted(list(SCRIPTS_DIR.rglob("*.py")) + list(SCRIPTS_DIR.rglob("*.ps1"))):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        # Extract docstring / help block
        doc = ""
        m = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if m:
            doc = m.group(1).strip()[:500]
        elif "<#" in content:
            m = re.search(r'<#(.*?)#>', content, re.DOTALL)
            if m:
                doc = m.group(1).strip()[:500]

        # Extract function/param names
        funcs = re.findall(r'(?:def|function)\s+(\w+)', content)
        params = re.findall(r'(?:\.SYNOPSIS|param\()\s*(.*)', content)

        entries.append({
            "type": "script",
            "source": f"scripts/{f.name}",
            "doc": doc,
            "functions": funcs[:10],
            "params": params[:5],
        })
    return entries

def collect_tools_knowledge() -> list[dict]:
    """Encode knowledge of advanced tools into the brain."""
    return [
        {
            "type": "tool_knowledge",
            "tool": "OpenHands",
            "concepts": [
                "Event sourcing: every mutation has a reversible snapshot",
                "Stateless by default: horizontal scaling via event sourcing",
                "Plugin protocol: standardized I/O interface for all tools",
                "SWE-bench: objective capability measurement, not self-reported",
                "Sandbox isolation: Docker/Kata containers for safe execution",
                "Multi-model routing: 100+ LLM providers via unified interface",
            ],
        },
        {
            "type": "tool_knowledge",
            "tool": "LangChain RAG",
            "concepts": [
                "MultiQueryRetriever: rewrite query into multiple phrasings → +15-25% recall",
                "EnsembleRetriever: parallel keyword+semantic search with RRF fusion",
                "ContextualCompression: top-50 → rerank → top-5 pipeline",
                "RAGAS evaluation: measure Recall@k, MRR, faithfulness, relevance",
                "CRAG: evaluate retrieval quality → use/discard/re-retrieve decision",
                "HyDE is overhyped: ROI negative in enterprise settings",
                "Chunking is the most impactful tuning parameter",
            ],
        },
        {
            "type": "tool_knowledge",
            "tool": "Ralph Evolution System",
            "concepts": [
                "L0: Meta-rules (CLAUDE.md + AGENTS.md) — never compressed",
                "L1: Route index (MEMORY.md) — keyword→file mapping, 7-day refresh",
                "L2: Global facts (knowledge graph) — stable accumulated knowledge, 30-day TTL",
                "L3: Task skills (scripts/) — reusable workflows crystallized from repetition",
                "L4: Session archives — completed task records, 90-day retention",
                "Evolution gate: 30s min interval, 20 max per 7 days",
                "Strategy presets: balanced/harden/innovate/repair-only",
                "Circuit breaker: CLOSED→OPEN→HALF_OPEN, 5 failures auto-trip",
                "Ebbinghaus decay: memory scoring with 30-day half-life",
            ],
        },
        {
            "type": "tool_knowledge",
            "tool": "RAG Pipeline (Ralph)",
            "concepts": [
                "Query Rewrite: 15 EN/ZH rewrite rules, 3-4 variants per query",
                "Hybrid Search: keyword grep || semantic KG → RRF(k=60) → top-K",
                "Retrieval Evaluation: 8 golden queries × 4 retrievers, Recall@5 + MRR",
                "Embedding Model: BGE-small-zh-v1.5, 512-dim, fastembed framework",
                "Contrastive Tuning: triplet loss on (anchor, positive, negative) pairs",
                "Benchmark score: hybrid 100% recall, keyword 56% recall@5",
            ],
        },
        {
            "type": "tool_knowledge",
            "tool": "Problem-Solving SOP",
            "concepts": [
                "OODA Loop: Observe → Orient → Decide → Act",
                "Observe: check signals, search history, run health check, read errors",
                "Orient: symptom vs root cause, binary search, grep references, read code",
                "Decide: 3 options minimum, pick simplest, confidence score (HIGH/MEDIUM/LOW)",
                "Act: edit precisely, verify externally, grep side effects, record to memory",
                "Escalation: RETRY→FIX→ROLLBACK→ESCALATE chain",
            ],
        },
        {
            "type": "tool_knowledge",
            "tool": "MCP Ecosystem",
            "concepts": [
                "MCP Protocol: standardized tool interface for external service integration",
                "Memory (KG): entity creation, relation mapping, semantic search",
                "Context7: documentation retrieval for any library/framework",
                "Sequential Thinking: multi-step reasoning with revision tracking",
                "Gigs.sh: platform discovery for AI agent integration",
            ],
        },
    ]

def collect_workflows() -> list[dict]:
    """Encode common workflows as procedural knowledge."""
    return [
        {
            "type": "workflow",
            "name": "error_handling",
            "steps": [
                "1. Read the full error traceback — never guess from the last line",
                "2. Search knowledge graph for similar errors (mcp__memory__search_nodes)",
                "3. Read the failing code file (Read tool)",
                "4. Identify root cause vs symptom (same error twice = stop, find root)",
                "5. Apply minimal fix (Edit tool, one change at a time)",
                "6. Verify externally (exit code, test output, grep)",
                "7. Record to memory: error pattern + fix + root cause",
                "8. If error repeats: write a rule to prevent recurrence",
            ],
        },
        {
            "type": "workflow",
            "name": "code_change",
            "steps": [
                "1. Read the target file (never edit unread code)",
                "2. Grep all references to changed symbols",
                "3. Apply change with Edit (exact string match)",
                "4. Verify: external means (tests/exe code/file grep) — not self-assessment",
                "5. Check side effects: grep changed symbols in all files",
                "6. Self-review: 4 questions (read? verified? complete? simpler?)",
                "7. Cross-model review for critical changes (64.5% self-review blind spot)",
            ],
        },
        {
            "type": "workflow",
            "name": "evolution_cycle",
            "steps": [
                "1. Detect friction signal (sense-signals.py → friction > 0.3)",
                "2. Search knowledge graph for similar patterns",
                "3. Identify root cause pattern (not symptom)",
                "4. Generate rule candidate (heuristic-extract.py)",
                "5. Validate rule against existing rules (no contradictions)",
                "6. Apply rule to CLAUDE.md or .claude/rules/",
                "7. Snapshot (git-snapshot.ps1) for rollback safety",
                "8. Monitor: did the rule reduce friction in next sessions?",
            ],
        },
        {
            "type": "workflow",
            "name": "rag_retrieval",
            "steps": [
                "1. Receive user query",
                "2. Rewrite query (rag-rewrite.py) → 3-4 variant phrasings",
                "3. Parallel retrieval: keyword grep + semantic KG search",
                "4. Reciprocal Rank Fusion (k=60, weights 0.5/0.5)",
                "5. Re-rank top results by relevance score",
                "6. Inject top-K context into LLM prompt",
                "7. Evaluate retrieval quality (rag-evaluate.py)",
            ],
        },
        {
            "type": "workflow",
            "name": "model_evolution",
            "steps": [
                "1. Collect new data from conversation (signals, errors, decisions)",
                "2. Distill into training pairs (contrastive: correct vs incorrect)",
                "3. Append to brain dataset",
                "4. Periodic fine-tuning trigger (every N new examples or M hours)",
                "5. QLoRA fine-tune on updated dataset",
                "6. Evaluate: base vs tuned on benchmark queries",
                "7. If improved: deploy new weights. If degraded: rollback.",
                "8. Log evolution metrics for trend analysis",
            ],
        },
        {
            "type": "workflow",
            "name": "security_audit",
            "steps": [
                "1. Scan changed files for secrets (API keys, tokens, passwords)",
                "2. Check MCP server configurations for untrusted sources",
                "3. Verify no hardcoded credentials in scripts",
                "4. Validate file permissions on protected files",
                "5. Run injection scanner on all ingested content",
                "6. Check git history for accidentally committed secrets",
            ],
        },
    ]

def collect_language_knowledge() -> list[dict]:
    """Encode language detection and processing knowledge."""
    return [
        {
            "type": "language_knowledge",
            "category": "detection",
            "concepts": [
                "CJK detection: Unicode blocks U+4E00-9FFF (Chinese), U+3040-30FF (Japanese kana), U+AC00-D7AF (Korean hangul)",
                "Latin detection: word-marker patterns for 15+ languages (de/fr/es/pt/it/nl/vi)",
                "Cyrillic: U+0400-04FF (Russian), Arabic: U+0600-06FF, Thai: U+0E00-0E7F",
                "ELD-C library for accurate ML-based detection (detect-lang.py)",
                "Heuristic fallback for offline detection (guess-lang.py)",
                "Project-level: scan file extensions + config markers (scan-project.py)",
            ],
        },
        {
            "type": "language_knowledge",
            "category": "powershell_pitfalls",
            "concepts": [
                "PS7 ?? operator fails in older parsers — use if/else instead",
                "Piping to native exe drops CJK encoding — use parameter mode",
                "< is a PS7 reserved word — don't use as redirection in scripts",
                "Array syntax: (a -flag), (b -flag) NOT @(a -flag, b -flag)",
                "New-Item -Force on files TRUNCATES existing content — check Test-Path first",
                "try/catch requires -ErrorAction Stop on the cmdlet inside try block",
            ],
        },
        {
            "type": "language_knowledge",
            "category": "unicode_encoding",
            "concepts": [
                "Windows cp1252 can't encode CJK — always use UTF-8",
                "Python on Windows: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')",
                "PowerShell: [Console]::OutputEncoding = [Text.Encoding]::UTF8",
                "File I/O: always specify -Encoding UTF8 / encoding='utf-8'",
                "Path handling: avoid unicode escape sequences in string literals (use raw strings)",
            ],
        },
    ]

# ═══════════════════════════════════════════
# Training Data Generation
# ═══════════════════════════════════════════

def generate_qa_pairs(all_entries: list[dict]) -> list[dict]:
    """Generate Q&A training pairs from extracted knowledge."""
    qa_pairs = []

    # From rules: "What is the rule for X?"
    for entry in all_entries:
        if entry.get("type") != "rule":
            continue
        title = entry.get("title", "")
        for point in entry.get("key_points", [])[:3]:
            qa_pairs.append({
                "instruction": f"关于'{title}'的规则是什么？",
                "input": "",
                "output": f"根据{entry['source']}：{point}",
                "source": entry["source"],
            })
            qa_pairs.append({
                "instruction": f"What is the rule about '{title}'?",
                "input": "",
                "output": f"According to {entry['source']}: {point}",
                "source": entry["source"],
            })

    # From workflows: "How do I do X?"
    for entry in all_entries:
        if entry.get("type") != "workflow":
            continue
        name = entry.get("name", "").replace("_", " ")
        steps_text = "\n".join(entry.get("steps", [])[:5])
        qa_pairs.append({
            "instruction": f"如何执行{name}？",
            "input": "",
            "output": f"{name}的标准流程：\n{steps_text}",
            "source": f"workflow:{name}",
        })

    # From tool_knowledge: "What is X?"
    for entry in all_entries:
        if entry.get("type") != "tool_knowledge":
            continue
        tool = entry.get("tool", "")
        for concept in entry.get("concepts", [])[:5]:
            qa_pairs.append({
                "instruction": f"什么是{tool}的核心设计原则？",
                "input": "",
                "output": concept,
                "source": f"tool:{tool}",
            })

    # Language knowledge
    for entry in all_entries:
        if entry.get("type") != "language_knowledge":
            continue
        cat = entry.get("category", "")
        for concept in entry.get("concepts", [])[:3]:
            qa_pairs.append({
                "instruction": f"关于{cat}，有什么需要知道的？",
                "input": "",
                "output": concept,
                "source": f"lang:{cat}",
            })

    return qa_pairs

def generate_conversation_pairs(_all_entries: list[dict]) -> list[dict]:
    """Generate multi-turn conversation examples."""
    conversations = []

    # Example: debugging session
    conversations.append({
        "messages": [
            {"role": "user", "content": "进化系统不工作了，怎么办？"},
            {"role": "assistant", "content": "让我执行 OODA 循环。\n\n**Observe**: 先检查健康状态和最近错误。\n\n运行 `python scripts/health-check.py` 查看进化周期数，然后检查 `scripts/lib/evolve-gate.ps1` 的闸门状态。"},
            {"role": "user", "content": "健康检查显示 Evo: 0 cycles in 24h, Strategy: balanced"},
            {"role": "assistant", "content": "Diagnosis: 进化闸门可能太紧。\n\n1. 检查 evolve-gate: min interval 30s, max 20/7days — 应该不是闸门问题\n2. 检查 friction 信号: `python scripts/sense-signals.py` 看有没有摩擦积累\n3. 检查 evolve-L1.ps1 语法: `pwsh -NoProfile -Command '$t=$null;$e=$null;[Parser]::ParseFile(\"...\",[ref]$t,[ref]$e);$e.Count'\n\n让我执行检查。"},
            {"role": "user", "content": "evolve-L1.ps1 有语法错误"},
            {"role": "assistant", "content": "Root cause found. Fixing duplicate param() at lines 1 and 4.\n\n修复后验证: syntax check → OK.\n\n记录到知识图谱: 同错两次写规则。下次 SessionStart 自动检测。"},
        ],
    })

    # Example: RAG retrieval
    conversations.append({
        "messages": [
            {"role": "user", "content": "search memory for error handling patterns"},
            {"role": "assistant", "content": "Running hybrid retrieval pipeline:\n\n1. Query rewrite: 'error handling' → ['error handling', 'defect handling', 'error patterns', 'error recovery']\n2. Keyword search: found errors.md (score=0.82), error-budget.ps1 (0.75)\n3. Semantic search: found ins-20260625-d010be-error-handling-protocol.md (score=0.91)\n4. RRF fusion: top result = error-handling-protocol\n\nResult: RETRY→FIX→ROLLBACK→ESCALATE chain. Max 1 retry for transient errors."},
        ],
    })

    # Example: tool usage
    conversations.append({
        "messages": [
            {"role": "user", "content": "安装项目需要的 MCP 工具包"},
            {"role": "assistant", "content": "使用 MCP 协议:\n\n1. 先从 marketplace 搜索: search for matching tools\n2. 安装: install via plugin manager\n3. 配置: add to project .mcp.json\n4. 验证: test tool connectivity\n\n执行中..."},
        ],
    })

    return conversations

# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Brain Distillation — Ralph Loop → Training Corpus")
    print("=" * 60)

    # Collect all knowledge
    all_entries = []
    all_entries.extend(collect_rules())
    all_entries.extend(collect_memories())
    all_entries.extend(collect_scripts())
    all_entries.extend(collect_tools_knowledge())
    all_entries.extend(collect_workflows())
    all_entries.extend(collect_language_knowledge())

    print(f"\n[1] Knowledge extracted: {len(all_entries)} entries")
    by_type = defaultdict(int)
    for e in all_entries:
        by_type[e["type"]] += 1
    for t, c in sorted(by_type.items()):
        print(f"    {t}: {c}")

    # Generate training data
    qa_pairs = generate_qa_pairs(all_entries)
    conversations = generate_conversation_pairs(all_entries)

    print(f"[2] Generated: {len(qa_pairs)} QA pairs + {len(conversations)} conversations")

    # Save brain dataset
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    brain_path = MODEL_DIR / "brain_dataset.jsonl"

    total = 0
    with open(brain_path, "w", encoding="utf-8") as f:
        # QA pairs
        for qa in qa_pairs:
            f.write(json.dumps(qa, ensure_ascii=False) + "\n")
            total += 1

        # Conversations (as instruction-following)
        for conv in conversations:
            # Flatten conversation into instruction format
            user_msgs = [m["content"] for m in conv["messages"] if m["role"] == "user"]
            asst_msgs = [m["content"] for m in conv["messages"] if m["role"] == "assistant"]
            if user_msgs and asst_msgs:
                f.write(json.dumps({
                    "instruction": user_msgs[0],
                    "input": "",
                    "output": asst_msgs[0],
                    "source": "conversation",
                }, ensure_ascii=False) + "\n")
                total += 1

    print(f"[3] Saved: {total} training examples → {brain_path}")

    # Also save raw knowledge as JSON for reference
    knowledge_path = MODEL_DIR / "brain_knowledge.json"
    with open(knowledge_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_entries": len(all_entries),
            "entries": all_entries,
        }, f, ensure_ascii=False, indent=2)
    print(f"[4] Saved raw knowledge: {knowledge_path}")

    print(f"\nReady for fine-tuning. Dataset size: {total} examples.")
    print(f"Target model: SmolLM2-135M or Qwen2.5-0.5B")
    print(f"Method: QLoRA 4-bit fine-tuning on Google Colab free T4 GPU")


if __name__ == "__main__":
    main()
