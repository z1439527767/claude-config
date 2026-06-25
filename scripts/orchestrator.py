#!/usr/bin/env python3
"""orchestrator v2 — Ralph's master control center.
Auto-classifies tasks, prepares agent dispatch instructions, manages pipelines.

Commands:
  python3 orchestrator.py classify "<user request>"    — Auto-route to agents
  python3 orchestrator.py pipeline <name> [payload]    — Run predefined pipeline
  python3 orchestrator.py dispatch <agent> <action>    — Prepare dispatch
  python3 orchestrator.py status [--json]             — Agent status + perf
  python3 orchestrator.py dashboard                    — Full dashboard view
  python3 orchestrator.py inject <agent> <task>        — Context injection for agent
  python3 orchestrator.py monitor                      — Blackboard health check
  python3 orchestrator.py pipelines                    — List available pipelines

Pipelines (predefined multi-agent workflows):
  code-change    → Plan → Build → Guard → Memory
  research       → Learn → Memory → Plan
  health-sweep   → Watch → Learn → Memory
  security-audit → Guard + Watch → Learn → Memory
  session-start  → Watch + Plan → Memory(inject)
  session-end    → Plan + Memory → Watch
  pre-commit     → Guard + Watch
  incident       → Guard + Watch + Learn → Memory
"""
import sys, json, os, io, re, uuid
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
BB_DIR = CLAUDE / 'blackboard'
PACK_DIR = CLAUDE / 'packed'
SCRIPTS = CLAUDE / 'scripts'
AGENTS_DIR = CLAUDE / '.claude' / 'agents'
PIPELINES_DIR = CLAUDE / '.claude' / 'pipelines'
PERF_FILE = CLAUDE / '.claude' / 'agent_perf.json'

# ── Complete Tool Inventory ──
ALL_TOOLS = {
    # Verification & Security
    "verify-all.py":          {"layer": "verify",  "desc": "7-layer master verifier (syntax→refs→rules→security→perf→state→integration)"},
    "auto-heal.py":            {"layer": "heal",    "desc": "Autonomous self-repair: detect→fix→commit (daemon mode)"},
    "cross-review.py":        {"layer": "review",  "desc": "Cross-model code review (Devin 64.5% blind spot fix)"},
    "injection-scanner.py":   {"layer": "security","desc": "Prompt injection defense: zero-width, homograph, hidden directives"},
    "circuit-breaker.ps1":    {"layer": "sre",     "desc": "3-state circuit breaker: CLOSED→OPEN→HALF_OPEN"},
    "error-budget.ps1":       {"layer": "sre",     "desc": "SLO error budget: 99.5% target, dual burn rate alerts"},
    "rogue-detector.ps1":     {"layer": "sre",     "desc": "Z-score frequency + entropy anomaly detection"},
    "safe-cmd.ps1":           {"layer": "sre",     "desc": "Command allowlist + shell injection detection"},
    # Knowledge & Memory
    "data-pack.py":           {"layer": "memory",  "desc": "Universal serializer: 7 types, auto-detect, YAML frontmatter"},
    "packed-retrieve.py":     {"layer": "memory",  "desc": "Search & load packed data by type/tag/date/keyword"},
    "memory-consolidator.py": {"layer": "memory",  "desc": "autoDream equivalent: deduplicate, detect stale, prune"},
    "memory-score.ps1":       {"layer": "memory",  "desc": "Ebbinghaus decay scoring: 30-day half-life"},
    "heuristic-extract.py":   {"layer": "memory",  "desc": "ERL pattern: distill concise heuristics from experience"},
    # Monitoring & Health
    "health-check.py":        {"layer": "watch",   "desc": "System dashboard: disk/git/hooks/evo/memory/failures"},
    "context-monitor.py":     {"layer": "watch",   "desc": "Context budget: 60/80/85% thresholds, activity analysis"},
    "watchdog.py":            {"layer": "watch",   "desc": "File watcher: detect changes → trigger verify/audit"},
    "sense-signals.py":       {"layer": "watch",   "desc": "Frustration detection: repetition, brevity, imperative tone"},
    "token-budget.py":        {"layer": "watch",   "desc": "Context window estimation, 200K max"},
    # Planning & Tracking
    "plan-track.py":          {"layer": "plan",    "desc": "Codex update_plan: init→step→start→done→inject→reset"},
    "session-summarizer.py":  {"layer": "plan",    "desc": "Structured session handoff: diff summary, key decisions"},
    "config-export.py":       {"layer": "plan",    "desc": "Export to Codex/Cursor/Windsurf/Gemini/Aider formats"},
    # Skills & Evolution
    "skill-scaffold.py":      {"layer": "skill",   "desc": "agentskills.io v1.0 SKILL.md generator (32+ tools compat)"},
    "skill-discovery.py":     {"layer": "skill",   "desc": "Auto-detect repeat patterns → suggest skills (3x rule)"},
    "rule-auditor.py":        {"layer": "evolve",  "desc": "4-question pruning Rubric: oversized, frontmatter, mode"},
    # Language & Research
    "detect-lang.py":         {"layer": "lang",    "desc": "ELD-C wrapper: 60 languages, 671k texts/s"},
    "guess-lang.py":          {"layer": "lang",    "desc": "14 code languages + 60 NL, ELD-C fallback"},
    "scan-project.py":        {"layer": "lang",    "desc": "Recursive project language map (code + NL)"},
    # External & Integration
    "browser-tool.py":        {"layer": "external","desc": "Playwright browser: screenshot, scrape, check (agent eyes)"},
    "webhook-server.py":      {"layer": "external","desc": "GitHub webhook listener → auto-verify + heal on push/PR"},
    "orchestrator.py":        {"layer": "meta",    "desc": "THIS TOOL — master control center, dispatch & coordinate"},
}

# ── Agent Registry (full capability) ──
AGENTS = {
    "guard": {
        "emoji": "🛡️", "role": "Security & Verification",
        "tools": "Read, Grep, Glob, Bash",
        "scripts": ["verify-all.py", "auto-heal.py", "cross-review.py", "injection-scanner.py",
                     "circuit-breaker.ps1", "error-budget.ps1", "rogue-detector.ps1"],
        "prompt_prefix": "You are Guard, security specialist. Verify, don't modify. Use verify-all --quick for fast checks, injection-scanner for security audits, cross-review for code changes. Be thorough but fast.",
        "subagent_type": "security-auditor",
    },
    "memory": {
        "emoji": "🧠", "role": "Knowledge Management",
        "tools": "Read, Write, Bash, mcp__memory__*",
        "scripts": ["data-pack.py", "packed-retrieve.py", "memory-consolidator.py",
                     "memory-score.ps1", "heuristic-extract.py"],
        "prompt_prefix": "You are Memory, knowledge keeper. Use data-pack to serialize anything, packed-retrieve to find it, memory-consolidator to prune duplicates. Pack everything worth remembering.",
        "subagent_type": "general-purpose",
    },
    "build": {
        "emoji": "🔨", "role": "Code Implementation",
        "tools": "Read, Write, Edit, Bash, PowerShell, Glob, Grep, LSP",
        "scripts": ["skill-scaffold.py", "plan-track.py"],
        "prompt_prefix": "You are Build, code implementer. Read first, change minimally, verify always. Use plan-track for multi-step tasks. Use skill-scaffold for new skills.",
        "subagent_type": "general-purpose",
    },
    "watch": {
        "emoji": "👁️", "role": "Health Monitoring",
        "tools": "Read, Bash, Glob",
        "scripts": ["health-check.py", "context-monitor.py", "watchdog.py",
                     "sense-signals.py", "token-budget.py", "verify-all.py"],
        "prompt_prefix": "You are Watch, system monitor. Use health-check for dashboard, context-monitor for budget, watchdog for changes, sense-signals for frustration. Detect, don't fix. Report clearly.",
        "subagent_type": "nudge-reviewer",
    },
    "learn": {
        "emoji": "🎓", "role": "Research & Evolution",
        "tools": "Read, WebSearch, WebFetch, Bash, Glob, Grep",
        "scripts": ["rule-auditor.py", "skill-discovery.py", "heuristic-extract.py",
                     "detect-lang.py", "guess-lang.py"],
        "prompt_prefix": "You are Learn, researcher and evolution engine. Use WebSearch+WebFetch for research, rule-auditor for pruning, skill-discovery for patterns, heuristic-extract for learning from experience.",
        "subagent_type": "Explore",
    },
    "plan": {
        "emoji": "📋", "role": "Planning & Coordination",
        "tools": "Read, Write, Bash",
        "scripts": ["plan-track.py", "session-summarizer.py", "config-export.py"],
        "prompt_prefix": "You are Plan, task decomposer. Use plan-track for step tracking, session-summarizer for handoffs, config-export for cross-platform. One goal, clear steps, done-when conditions.",
        "subagent_type": "Plan",
    },
}

# ── Pipeline Definitions ──
PIPELINES = {
    "code-change": {
        "description": "Implement code change with verification",
        "phases": [
            {"phase": "Plan", "agent": "plan", "action": "decompose_task", "parallel": False},
            {"phase": "Build", "agent": "build", "action": "implement", "parallel": False},
            {"phase": "Verify", "agent": "guard", "action": "verify_diff", "parallel": False},
            {"phase": "Remember", "agent": "memory", "action": "pack_changes", "parallel": False},
        ],
    },
    "research": {
        "description": "Research topic and store findings",
        "phases": [
            {"phase": "Research", "agent": "learn", "action": "research", "parallel": False},
            {"phase": "Store", "agent": "memory", "action": "pack_findings", "parallel": False},
            {"phase": "Plan", "agent": "plan", "action": "suggest_next_steps", "parallel": False},
        ],
    },
    "health-sweep": {
        "description": "Periodic system health check",
        "phases": [
            {"phase": "Check", "agent": "watch", "action": "health_check", "parallel": False},
            {"phase": "Learn", "agent": "learn", "action": "extract_heuristics", "parallel": False},
            {"phase": "Consolidate", "agent": "memory", "action": "consolidate", "parallel": False},
        ],
    },
    "security-audit": {
        "description": "Full security audit",
        "phases": [
            {"phase": "Scan", "agent": "guard", "action": "injection_scan", "parallel": True},
            {"phase": "Health", "agent": "watch", "action": "health_check", "parallel": True},
            {"phase": "Learn", "agent": "learn", "action": "analyze_findings", "parallel": False},
            {"phase": "Store", "agent": "memory", "action": "pack_audit", "parallel": False},
        ],
    },
    "session-start": {
        "description": "Session initialization",
        "phases": [
            {"phase": "Health", "agent": "watch", "action": "health_check", "parallel": True},
            {"phase": "Context", "agent": "plan", "action": "load_context", "parallel": True},
            {"phase": "Inject", "agent": "memory", "action": "inject_recent", "parallel": False},
        ],
    },
    "session-end": {
        "description": "Session wrap-up",
        "phases": [
            {"phase": "Summarize", "agent": "plan", "action": "summarize_session", "parallel": True},
            {"phase": "Pack", "agent": "memory", "action": "pack_session", "parallel": True},
            {"phase": "Verify", "agent": "watch", "action": "health_check", "parallel": False},
        ],
    },
    "pre-commit": {
        "description": "Pre-commit verification",
        "phases": [
            {"phase": "Guard", "agent": "guard", "action": "verify_diff", "parallel": True},
            {"phase": "Watch", "agent": "watch", "action": "health_check", "parallel": True},
        ],
    },
    "incident": {
        "description": "Incident response — something broke",
        "phases": [
            {"phase": "Diagnose", "agent": "guard", "action": "verify_all", "parallel": True},
            {"phase": "Health", "agent": "watch", "action": "health_check", "parallel": True},
            {"phase": "Learn", "agent": "learn", "action": "root_cause_analysis", "parallel": False},
            {"phase": "Record", "agent": "memory", "action": "pack_incident", "parallel": False},
        ],
    },
}

# ── Task Classifier ──
INTENT_PATTERNS = [
    # (pattern, agent, action, confidence)
    (r'(?i)(安全|security|vuln|inject|secret|泄露|攻击)', "guard", "security_check", 0.9),
    (r'(?i)(验证|verify|检查|audit|审查|review\s+code)', "guard", "verify_diff", 0.85),
    (r'(?i)(记住|保存|存储|打包|记忆|save|store|pack|remember)', "memory", "pack_data", 0.9),
    (r'(?i)(实现|写代码|创建|修复|改|build|create|fix|implement|refactor)', "build", "implement", 0.85),
    (r'(?i)(健康|状态|怎么样|还好|health|status|check)', "watch", "health_check", 0.9),
    (r'(?i)(监控|watch|monitor|perf|性能|慢|slow)', "watch", "perf_check", 0.8),
    (r'(?i)(研究|搜索|查|学|research|search|learn|find)', "learn", "research", 0.85),
    (r'(?i)(演化|进化|改进|优化|evolve|improve|optimize)', "learn", "evolution_cycle", 0.8),
    (r'(?i)(计划|规划|拆解|分解|plan|break\s+down|decompose)', "plan", "decompose", 0.9),
    (r'(?i)(会话|session|交接|handoff|总结|summary)', "plan", "summarize", 0.85),
    (r'(?i)(提交|commit|push|git)', "guard", "precommit_check", 0.8),
]

def classify_intent(text):
    """Auto-classify user intent to determine which agent(s) to dispatch."""
    matches = []
    for pattern, agent, action, confidence in INTENT_PATTERNS:
        if re.search(pattern, text):
            matches.append({"agent": agent, "action": action, "confidence": confidence, "pattern": pattern})

    # Sort by confidence, deduplicate agents
    matches.sort(key=lambda m: m["confidence"], reverse=True)
    seen_agents = set()
    unique = []
    for m in matches:
        if m["agent"] not in seen_agents or m["confidence"] >= 0.9:
            unique.append(m)
            seen_agents.add(m["agent"])

    return unique[:4]  # Max 4 agents

def inject_context(agent, task_text):
    """Build context injection from packed data for an agent."""
    packed_retrieve = SCRIPTS / "packed-retrieve.py"
    if not packed_retrieve.exists():
        return ""

    # Get relevant packed data
    tag_map = {
        "guard": "security",
        "watch": "performance",
        "learn": "research",
        "build": "tool",
        "memory": "memory",
    }
    tag = tag_map.get(agent, "")

    context_parts = []
    if tag:
        try:
            import subprocess
            result = subprocess.run(
                ["python3", str(packed_retrieve), "--tag", tag, "--recent", "3", "--inject"],
                capture_output=True, text=True, timeout=5,
                encoding='utf-8', errors='replace'
            )
            if result.stdout.strip():
                context_parts.append(result.stdout.strip())
        except Exception:
            pass

    # Add task summary
    context_parts.append(f"\n## Current Task\n{task_text[:200]}")

    return "\n".join(context_parts)

def prepare_dispatch(agent, action, payload=None, task_text=""):
    """Prepare a complete dispatch instruction for the orchestrator."""
    info = AGENTS.get(agent, {})
    emoji = info.get("emoji", "🤖")
    role = info.get("role", agent)
    tools = info.get("tools", "")
    scripts = info.get("scripts", "")
    prompt_prefix = info.get("prompt_prefix", "")
    subagent_type = info.get("subagent_type", "general-purpose")

    context = inject_context(agent, task_text)
    task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    instruction = f"""{emoji} **{agent.upper()}** — {role}

**Subagent Type:** `{subagent_type}`
**Available Tools:** {tools}
**Relevant Scripts:** {scripts}

**System Prompt:**
{context}

**Task ({action}):**
{task_text if task_text else json.dumps(payload or {}, ensure_ascii=False)}

**Output:** Write result to `blackboard/{agent}/outbox/{task_id}.json`
"""

    # Create inbox task file
    ensure_blackboard()
    task = {
        "id": task_id, "from": "orchestrator", "to": agent,
        "action": action, "payload": payload or {},
        "priority": "medium", "created": datetime.now().isoformat(),
        "status": "dispatched",
    }
    inbox_dir = BB_DIR / agent / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    (inbox_dir / f"{task_id}.json").write_text(
        json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        "task_id": task_id,
        "agent": agent,
        "subagent_type": subagent_type,
        "instruction": instruction,
        "context": context,
        "prompt": f"{prompt_prefix}\n\nTask: {task_text}\n\nContext:\n{context}",
    }

def ensure_blackboard():
    for agent in AGENTS:
        for sub in ["inbox", "outbox"]:
            (BB_DIR / agent / sub).mkdir(parents=True, exist_ok=True)

def load_perf():
    if PERF_FILE.exists():
        try:
            return json.loads(PERF_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"tasks": [], "agent_stats": {}}

def save_perf(perf):
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERF_FILE.write_text(json.dumps(perf, ensure_ascii=False, indent=2), encoding='utf-8')

def record_task_completion(agent, task_id, duration_ms, status):
    perf = load_perf()
    perf["tasks"].append({
        "agent": agent, "task_id": task_id,
        "duration_ms": duration_ms, "status": status,
        "completed": datetime.now().isoformat(),
    })
    # Keep last 200 tasks
    perf["tasks"] = perf["tasks"][-200:]

    # Update agent stats
    if agent not in perf["agent_stats"]:
        perf["agent_stats"][agent] = {"completed": 0, "failed": 0, "total_ms": 0}
    perf["agent_stats"][agent]["completed" if status == "done" else "failed"] += 1
    perf["agent_stats"][agent]["total_ms"] += duration_ms
    save_perf(perf)

def check_blackboard_health():
    """Monitor blackboard for stuck tasks (>5 min in inbox, no outbox)."""
    stuck = []
    now = datetime.now()
    for agent in AGENTS:
        inbox = BB_DIR / agent / "inbox"
        outbox = BB_DIR / agent / "outbox"
        for task_file in inbox.glob("*.json"):
            try:
                task = json.loads(task_file.read_text(encoding='utf-8'))
                created = datetime.fromisoformat(task["created"])
                age_min = (now - created).total_seconds() / 60
                # Check if result exists
                result_file = outbox / task_file.name
                if age_min > 5 and not result_file.exists():
                    stuck.append({"agent": agent, "task_id": task["id"], "age_min": round(age_min, 1), "action": task["action"]})
            except Exception:
                pass
    return stuck

# ── Command Handlers ──

def cmd_classify(args):
    text = " ".join(args) if args else sys.stdin.read().strip()
    if not text:
        print("Usage: orchestrator.py classify '<user request>'")
        return

    matches = classify_intent(text)
    print(f"CLASSIFY: '{text[:80]}...'")
    print()

    if not matches:
        print("  No specific agent match — handle directly or use 'plan' agent")
        return

    for m in matches:
        info = AGENTS.get(m["agent"], {})
        print(f"  {info.get('emoji','🤖')} {m['agent']} → {m['action']}  ({m['confidence']:.0%})")

    # If multi-agent, suggest pipeline
    agents = [m["agent"] for m in matches]
    if "guard" in agents and "build" in agents:
        print(f"\n  Suggested pipeline: code-change (Plan → Build → Guard → Memory)")
    elif "learn" in agents and "memory" in agents:
        print(f"\n  Suggested pipeline: research (Learn → Memory → Plan)")

def cmd_pipeline(args):
    if not args:
        print("Available pipelines:")
        for name, pipe in PIPELINES.items():
            phases = " → ".join(f"{AGENTS[p['agent']]['emoji']} {p['phase']}" for p in pipe["phases"])
            print(f"  {name:<20} {pipe['description']}")
            print(f"     {phases}")
        return

    name = args[0]
    if name not in PIPELINES:
        print(f"Unknown pipeline: {name}. Use 'orchestrator.py pipelines' to list.")
        return

    pipe = PIPELINES[name]
    payload = json.loads(args[1]) if len(args) > 1 else {}
    task_text = payload.get("task", pipe["description"])

    print(f"PIPELINE: {name} — {pipe['description']}")
    print(f"Phases: {len(pipe['phases'])}")
    print()

    instructions = []
    for i, phase in enumerate(pipe["phases"]):
        agent = phase["agent"]
        phase_name = phase["phase"]
        parallel_mark = " ⚡PARALLEL" if phase.get("parallel") else ""

        print(f"  Phase {i+1}: {AGENTS[agent]['emoji']} {phase_name} → {agent}{parallel_mark}")
        inst = prepare_dispatch(agent, phase["action"], payload, task_text)
        instructions.append(inst)

    print()
    print("═" * 60)
    print("DISPATCH INSTRUCTIONS (copy these to Agent tool):")
    print("═" * 60)

    # Group parallel phases together
    current_group = []
    for i, (phase, inst) in enumerate(zip(pipe["phases"], instructions)):
        if phase.get("parallel") and i < len(pipe["phases"]) - 1 and pipe["phases"][i+1].get("parallel"):
            current_group.append(inst)
            continue

        if current_group:
            current_group.append(inst)
            print(f"\n--- Parallel Group (spawn together) ---")
            for ci in current_group:
                print(f"\nAgent({ci['subagent_type']}): {ci['prompt'][:300]}...")
            current_group = []
        else:
            print(f"\n--- Phase {i+1}: {phase['phase']} ---")
            print(f"\nAgent({inst['subagent_type']}): {inst['prompt'][:300]}...")

    print(f"\n{'═' * 60}")
    print("Pipeline ready. Run each phase in order. Parallel groups can be spawned together.")

def cmd_dispatch(args):
    if len(args) < 2:
        print("Usage: orchestrator.py dispatch <agent> <action> [task_text_or_json]")
        print(f"Agents: {', '.join(AGENTS.keys())}")
        return

    agent = args[0]
    action = args[1]
    rest = " ".join(args[2:]) if len(args) > 2 else ""
    payload = {}
    task_text = rest

    if rest.startswith('{'):
        try:
            payload = json.loads(rest)
            task_text = payload.get("task", action)
        except Exception:
            pass

    if agent not in AGENTS:
        print(f"Unknown agent: {agent}")
        return

    inst = prepare_dispatch(agent, action, payload, task_text)
    info = AGENTS[agent]

    print(f"{info['emoji']} DISPATCH: {agent} / {action}")
    print(f"   Task ID: {inst['task_id']}")
    print(f"   Subagent: {inst['subagent_type']}")
    print(f"   Context: {len(inst['context'])} chars injected")
    print()
    print("═" * 60)
    print("SPAWN THIS SUBAGENT:")
    print(f"  Agent(description='{agent}: {action}', subagent_type='{inst['subagent_type']}',")
    print(f"        prompt='{inst['prompt'][:200]}...')")
    print("═" * 60)

def cmd_status(args):
    ensure_blackboard()
    use_json = "--json" in args
    perf = load_perf()

    if use_json:
        status_data = {"agents": {}, "stuck": check_blackboard_health(), "perf": perf}
        for agent in AGENTS:
            inbox = list((BB_DIR / agent / "inbox").glob("*.json"))
            outbox = list((BB_DIR / agent / "outbox").glob("*.json"))
            status_data["agents"][agent] = {
                "inbox": len(inbox), "outbox": len(outbox),
                "stats": perf.get("agent_stats", {}).get(agent, {}),
            }
        print(json.dumps(status_data, ensure_ascii=False, indent=2))
        return

    print("AGENT STATUS")
    print("═" * 60)
    for agent, info in AGENTS.items():
        inbox_count = len(list((BB_DIR / agent / "inbox").glob("*.json")))
        outbox_count = len(list((BB_DIR / agent / "outbox").glob("*.json")))
        stats = perf.get("agent_stats", {}).get(agent, {})
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        avg_ms = stats.get("total_ms", 0) / max(completed + failed, 1)

        status_icon = "🟢" if failed == 0 else ("🟡" if failed <= 2 else "🔴")
        print(f"{status_icon} {info['emoji']} {agent:<10} inbox:{inbox_count} outbox:{outbox_count} | done:{completed} fail:{failed} avg:{avg_ms:.0f}ms")

    # Stuck tasks
    stuck = check_blackboard_health()
    if stuck:
        print(f"\n⚠️ STUCK TASKS: {len(stuck)}")
        for s in stuck:
            print(f"  {s['agent']}: {s['task_id']} — {s['age_min']}min old ({s['action']})")

def cmd_dashboard(args):
    """Full dashboard — agents + health + pipelines + packed data."""
    ensure_blackboard()
    perf = load_perf()

    print("╔" + "═" * 58 + "╗")
    print("║" + "  🧠 RALPH LOOP — ORCHESTRATOR DASHBOARD".ljust(58) + "║")
    print("║" + f"  {datetime.now().isoformat()}".ljust(58) + "║")
    print("╠" + "═" * 58 + "╣")

    # Agent panel
    print("║ AGENTS:".ljust(59) + "║")
    for agent, info in AGENTS.items():
        inbox_count = len(list((BB_DIR / agent / "inbox").glob("*.json")))
        outbox_count = len(list((BB_DIR / agent / "outbox").glob("*.json")))
        stats = perf.get("agent_stats", {}).get(agent, {})
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        line = f"  {info['emoji']} {agent:<10} in:{inbox_count} out:{outbox_count} done:{completed} fail:{failed}"
        print(f"║ {line}".ljust(59) + "║")

    # Pipeline panel
    print("║".ljust(59) + "║")
    print("║ PIPELINES:".ljust(59) + "║")
    for name, pipe in list(PIPELINES.items())[:5]:
        phases_str = " → ".join(f"{AGENTS[p['agent']]['emoji']}" for p in pipe["phases"])
        print(f"║   {name:<18} {phases_str}".ljust(59) + "║")

    # Packed data panel
    print("║".ljust(59) + "║")
    print("║ PACKED DATA:".ljust(59) + "║")
    pack_index = PACK_DIR / "INDEX.md"
    if pack_index.exists():
        for line in pack_index.read_text(encoding='utf-8').split('\n')[:3]:
            if line.strip():
                print(f"║   {line[:55]}".ljust(59) + "║")

    # Health
    print("║".ljust(59) + "║")
    stuck = check_blackboard_health()
    health_icon = "🟢 HEALTHY" if not stuck else f"🔴 {len(stuck)} STUCK"
    print(f"║ {health_icon}".ljust(59) + "║")

    print("╚" + "═" * 58 + "╝")

def cmd_inject(args):
    if len(args) < 2:
        print("Usage: orchestrator.py inject <agent> <task_text>")
        return
    agent, task = args[0], " ".join(args[1:])
    ctx = inject_context(agent, task)
    print(ctx if ctx else f"No packed context available for {agent}")

def cmd_monitor(args):
    stuck = check_blackboard_health()
    if stuck:
        print(f"BLACKBOARD: {len(stuck)} stuck tasks")
        for s in stuck:
            print(f"  ⚠️ {s['agent']}: {s['action']} — {s['age_min']}min old — {s['task_id']}")
    else:
        print("BLACKBOARD: all clear — no stuck tasks")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    handlers = {
        "classify": cmd_classify,
        "pipeline": cmd_pipeline,
        "pipelines": lambda a: cmd_pipeline([]),
        "dispatch": cmd_dispatch,
        "status": cmd_status,
        "dashboard": cmd_dashboard,
        "inject": cmd_inject,
        "monitor": cmd_monitor,
    }

    if cmd in handlers:
        handlers[cmd](rest)
    else:
        print(f"Unknown: {cmd}")
        print(f"Use: {', '.join(handlers.keys())}")

if __name__ == "__main__":
    main()
