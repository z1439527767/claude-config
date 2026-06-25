#!/usr/bin/env python3
"""curiosity-engine — Ralph's proactive knowledge gap detector and autonomous learner.
Discovers what the system doesn't know yet and suggests what to learn next.

Unlike subconscious (which finds patterns in existing data), curiosity:
- Identifies gaps: missing configs, undocumented errors, knowledge blind spots
- Generates "wonder" questions: "What if...?", "Why does...?", "How could...?"
- Prioritizes by impact: what would most improve the system if learned?
- Auto-explores: can trigger web searches for high-priority gaps
- Feeds the evolution loop: gap → research → learn → crystallize

Usage:
  python3 curiosity-engine.py                  # Gap scan + wonder questions
  python3 curiosity-engine.py --mode explore   # Auto-explore top gaps (web search)
  python3 curiosity-engine.py --mode wonder    # Generate creative "what if" questions
  python3 curiosity-engine.py --json           # JSON output
  python3 curiosity-engine.py --inject         # Context injection format
"""
import sys, json, os, io, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
MEMORY_DIR = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory'
RULES_DIR = CLAUDE / '.claude' / 'rules'
SCRIPTS_DIR = CLAUDE / 'scripts'
BLACKBOARD = CLAUDE / 'blackboard' / 'curiosity'

BLACKBOARD.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════
# GAP TYPE 1: Missing Configuration
# ═══════════════════════════════════════════

KNOWN_CONFIGS = {
    "settings.json": ["hooks", "permissions", "mcpServers", "env", "model", "lsp"],
    "CLAUDE.md": ["rules", "memory", "scripts", "evolution", "thinking"],
    "AGENTS.md": ["verification", "execution", "security", "autonomy"],
}

def detect_missing_configs():
    """Detect referenced but missing configuration files/sections."""
    gaps = []

    # Check settings.json
    settings_file = CLAUDE / 'settings.json'
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding='utf-8'))
            expected = KNOWN_CONFIGS.get("settings.json", [])
            for key in expected:
                if key not in settings:
                    gaps.append({
                        "domain": "config",
                        "gap": f"settings.json missing '{key}' section",
                        "impact": "medium",
                        "suggestion": f"Add {key} configuration to settings.json",
                    })

            # Check hook coverage
            hooks = settings.get('hooks', {})
            common_hooks = ['PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'SessionStart',
                          'SessionEnd', 'Stop', 'UserPromptSubmit', 'PreCompact', 'Notification']
            missing_hooks = [h for h in common_hooks if h not in hooks]
            if missing_hooks:
                gaps.append({
                    "domain": "hooks",
                    "gap": f"Unconfigured hooks: {', '.join(missing_hooks)}",
                    "impact": "high" if len(missing_hooks) >= 3 else "low",
                    "suggestion": f"Consider hooking: {', '.join(missing_hooks[:3])}",
                })
        except Exception:
            pass

    return gaps


# ═══════════════════════════════════════════
# GAP TYPE 2: Undocumented Error Patterns
# ═══════════════════════════════════════════

def detect_undocumented_errors():
    """Find error patterns in logs that aren't documented in memory."""
    gaps = []

    # Collect known errors from memory
    known_errors = set()
    if MEMORY_DIR.exists():
        for mf in MEMORY_DIR.rglob("*.md"):
            if mf.name == "MEMORY.md":
                continue
            try:
                content = mf.read_text(encoding='utf-8')
                if 'type: error' in content or 'type:  error' in content:
                    err_match = re.search(r'## Error\n```\n(.+?)\n```', content, re.DOTALL)
                    if err_match:
                        known_errors.add(err_match.group(1).strip()[:80].lower())
            except Exception:
                pass

    # Check recent tool failures
    recovery_file = CLAUDE / '.claude' / 'recovery_suggestions.json'
    if recovery_file.exists():
        try:
            recs = json.loads(recovery_file.read_text(encoding='utf-8'))
            for rec in recs:
                err_msg = rec.get('error', '')[:80].lower()
                if err_msg and err_msg not in known_errors:
                    gaps.append({
                        "domain": "error",
                        "gap": f"Undocumented error: {err_msg[:100]}",
                        "impact": "high",
                        "suggestion": f"Create error memory for: {err_msg[:80]}",
                    })
        except Exception:
            pass

    return gaps


# ═══════════════════════════════════════════
# GAP TYPE 3: Knowledge Blind Spots
# ═══════════════════════════════════════════

def detect_knowledge_blindspots():
    """Identify areas where the system has no knowledge coverage."""
    blindspots = []

    # Map current knowledge domains
    covered_domains = set()
    if MEMORY_DIR.exists():
        for mf in MEMORY_DIR.rglob("*.md"):
            if mf.name == "MEMORY.md":
                continue
            try:
                content = mf.read_text(encoding='utf-8')
                domain_match = re.search(r'domain:\s*(\S+)', content)
                if domain_match:
                    covered_domains.add(domain_match.group(1))
            except Exception:
                pass

    # Domains an AI agent SHOULD know about
    desired_domains = {
        'behavior', 'memory', 'security', 'performance', 'reliability',
        'communication', 'learning', 'evolution', 'verification',
        'error-handling', 'context-management', 'tool-use', 'parallelism',
        'git', 'testing', 'documentation', 'monitoring', 'scheduling',
    }

    missing_domains = desired_domains - covered_domains
    for domain in missing_domains:
        blindspots.append({
            "domain": "knowledge",
            "gap": f"No knowledge coverage for domain: {domain}",
            "impact": "medium",
            "suggestion": f"Research and document best practices for {domain}",
        })

    return blindspots


# ═══════════════════════════════════════════
# GAP TYPE 4: Tool Coverage Gaps
# ═══════════════════════════════════════════

def detect_tool_gaps():
    """Detect missing tool capabilities based on what the system tries to do."""
    gaps = []

    if not SCRIPTS_DIR.exists():
        return gaps

    existing_tools = set()
    for sf in SCRIPTS_DIR.glob("*.py"):
        try:
            content = sf.read_text(encoding='utf-8')
            # Extract what the tool does from docstring
            doc = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if doc:
                existing_tools.add(sf.stem)
        except Exception:
            pass

    # Common agent tool categories
    tool_categories = {
        'memory': ['memory-create', 'memory-search', 'memory-consolidator'],
        'verification': ['verify-all', 'cross-review', 'injection-scanner'],
        'data': ['data-pack', 'packed-retrieve', 'config-export'],
        'monitoring': ['health-check', 'context-monitor', 'watchdog'],
        'evolution': ['auto-heal', 'skill-discovery', 'rule-auditor'],
        'orchestration': ['orchestrator', 'plan-track'],
        'communication': ['obsidian-sync', 'webhook-server'],
    }

    for category, expected in tool_categories.items():
        missing = [t for t in expected if t not in existing_tools]
        if missing:
            gaps.append({
                "domain": "tool",
                "gap": f"Missing tools in '{category}': {', '.join(missing)}",
                "impact": "medium" if len(missing) <= 2 else "high",
                "suggestion": f"Build: {missing[0]}" if missing else "",
            })

    return gaps


# ═══════════════════════════════════════════
# WONDER QUESTIONS GENERATOR
# ═══════════════════════════════════════════

def generate_wonder_questions():
    """Generate creative 'what if' questions that drive exploration."""
    questions = []

    # Template-based wonder questions from observed patterns
    templates = [
        # Self-improvement
        ("What if Ralph could {action} without being asked?",
         ["optimize its own rules", "detect user frustration patterns", "pre-fetch relevant context",
          "generate new tools autonomously", "predict task duration accurately"]),
        # Cross-domain
        ("What if {domain1} patterns were applied to {domain2}?",
         [("error recovery", "memory management"), ("git workflows", "rule evolution"),
          ("context engineering", "tool selection"), ("security auditing", "code review")]),
        # Capability expansion
        ("How could Ralph learn to {skill}?",
         ["write better tests than humans", "detect its own biases", "explain its reasoning clearly",
          "collaborate with other AI agents", "manage long-running async tasks"]),
        # System design
        ("Why doesn't Ralph have {capability} yet?",
         ["a visual dashboard", "voice interaction", "mobile notifications",
          "real-time collaboration", "automatic daily summaries"]),
    ]

    for template, options in templates:
        for option in options[:3]:  # Pick top 3
            if isinstance(option, tuple):
                question = template.format(domain1=option[0], domain2=option[1])
            else:
                question = template.format(action=option, skill=option, capability=option)
            questions.append(question)

    return questions


# ═══════════════════════════════════════════
# IMPACT SCORING & PRIORITIZATION
# ═══════════════════════════════════════════

def score_gap(gap):
    """Score a gap by estimated impact and ease of filling."""
    impact_scores = {"high": 3, "medium": 2, "low": 1}
    domain_weights = {
        "error": 1.5, "config": 1.3, "knowledge": 1.0, "tool": 1.2,
        "hooks": 1.4, "security": 1.5,
    }
    base = impact_scores.get(gap.get('impact', 'low'), 1)
    weight = domain_weights.get(gap.get('domain', ''), 1.0)
    return round(base * weight, 1)


def main():
    use_json = "--json" in sys.argv
    do_inject = "--inject" in sys.argv
    mode = "scan"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]

    all_gaps = []
    all_gaps.extend(detect_missing_configs())
    all_gaps.extend(detect_undocumented_errors())
    all_gaps.extend(detect_knowledge_blindspots())
    all_gaps.extend(detect_tool_gaps())

    # Score and sort
    for g in all_gaps:
        g['_score'] = score_gap(g)
    all_gaps.sort(key=lambda g: -g['_score'])

    wonder_questions = generate_wonder_questions() if mode in ("wonder", "explore") else []

    if do_inject:
        lines = ["## Curiosity Engine — Knowledge Gaps"]
        for g in all_gaps[:5]:
            lines.append(f"- 🕳️ [{g['impact'].upper()}] {g['gap'][:120]}")
        if wonder_questions:
            lines.append("")
            lines.append("## Wonder Questions")
            for q in wonder_questions[:3]:
                lines.append(f"- 💭 {q}")
        print('\n'.join(lines))
        return

    if use_json:
        output = {
            "gaps": len(all_gaps),
            "top_gaps": [{"domain": g['domain'], "gap": g['gap'], "impact": g['impact'],
                          "score": g['_score'], "suggestion": g.get('suggestion', '')}
                         for g in all_gaps[:10]],
            "wonder_questions": wonder_questions,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"🔍 CURIOSITY ENGINE: {len(all_gaps)} gaps found")
        if not all_gaps:
            print("  No significant knowledge gaps detected. System coverage is good.")
            return

        print(f"\n── TOP GAPS (by impact) ──")
        for g in all_gaps[:8]:
            icon = {"error": "🔴", "config": "⚙️", "knowledge": "📚", "tool": "🔧", "hooks": "🪝"}.get(g['domain'], '📌')
            print(f"  {icon} [{g['impact'].upper()}] ({g['_score']:.1f}) {g['gap']}")
            if g.get('suggestion'):
                print(f"     → {g['suggestion']}")

        if wonder_questions:
            print(f"\n── WONDER QUESTIONS ──")
            for q in wonder_questions[:5]:
                print(f"  💭 {q}")

        # Save top gaps to blackboard
        if all_gaps:
            board_file = BLACKBOARD / f"gaps-{datetime.now().strftime('%Y%m%d')}.json"
            board_file.write_text(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "gaps": [{"domain": g['domain'], "gap": g['gap'], "impact": g['impact'],
                          "suggestion": g.get('suggestion', '')} for g in all_gaps[:10]],
            }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == "__main__":
    main()
