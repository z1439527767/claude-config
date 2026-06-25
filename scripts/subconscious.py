#!/usr/bin/env python3
"""subconscious — Ralph's background processing engine.
Runs during idle periods. Processes accumulated data, detects subtle patterns,
makes unexpected connections, surfaces insights to conscious agents via blackboard.

Unlike conscious processing (direct task execution), subconscious:
- Runs async, never blocks user interaction
- Makes associative leaps across unrelated domains
- Surfaces "hunches" with confidence scores, not certainties
- Dreams: recombines memories to generate novel connections
- Writes insight cards to blackboard/subconscious/

Usage:
  python3 subconscious.py                  # Run all detectors once
  python3 subconscious.py --mode dream     # Creative recombination mode
  python3 subconscious.py --mode monitor   # Continuous monitoring (daemon)
  python3 subconscious.py --json           # JSON output for piping
  python3 subconscious.py --inject         # Output insight cards for context injection
"""
import sys, json, os, io, re, hashlib, random
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
MEMORY_DIR = CLAUDE / 'projects' / 'C--Users-z1439--claude' / 'memory'
BLACKBOARD = CLAUDE / 'blackboard' / 'subconscious'
SCRIPTS_DIR = CLAUDE / 'scripts'
RULES_DIR = CLAUDE / '.claude' / 'rules'
EVENTS_DIR = CLAUDE / '.claude'
SESSION_DIR = CLAUDE / '.claude' / 'session_history'

# Ensure blackboard exists
BLACKBOARD.mkdir(parents=True, exist_ok=True)

# ── Insight Card Format ──
# Each insight has: id, type, title, body, confidence, sources, created

def card_id(insight_type):
    ts = datetime.now().strftime("%Y%m%d%H%M")
    h = hashlib.sha256(f"{insight_type}{datetime.now().isoformat()}{random.random()}".encode()).hexdigest()[:6]
    return f"sub-{insight_type}-{ts}-{h}"

def write_card(insight_type, title, body, confidence, sources, tags=None):
    """Write an insight card to the blackboard."""
    cid = card_id(insight_type)
    now = datetime.now()
    card = {
        "id": cid,
        "type": insight_type,
        "title": title,
        "body": body,
        "confidence": confidence,
        "sources": sources,
        "tags": tags or [],
        "created": now.isoformat(),
        "acknowledged": False,
    }
    card_file = BLACKBOARD / f"{cid}.json"
    card_file.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding='utf-8')
    return card

def read_blackboard():
    """Read all unacknowledged insight cards."""
    cards = []
    if not BLACKBOARD.exists():
        return cards
    for f in sorted(BLACKBOARD.glob("sub-*.json")):
        try:
            card = json.loads(f.read_text(encoding='utf-8'))
            cards.append(card)
        except Exception:
            pass
    return cards

# ═══════════════════════════════════════════
# DETECTOR 1: Cross-Domain Pattern Detector
# ═══════════════════════════════════════════

def load_all_texts():
    """Load all available text data for pattern mining."""
    texts = {}

    # Memory files
    if MEMORY_DIR.exists():
        for mf in MEMORY_DIR.rglob("*.md"):
            if mf.name == "MEMORY.md" or '_archive' in str(mf):
                continue
            try:
                content = mf.read_text(encoding='utf-8')
                texts[f"memory:{mf.stem}"] = content
            except Exception:
                pass

    # Rules
    if RULES_DIR.exists():
        for rf in RULES_DIR.glob("*.md"):
            try:
                texts[f"rule:{rf.stem}"] = rf.read_text(encoding='utf-8')
            except Exception:
                pass

    # CLAUDE.local.md learnings
    local_md = CLAUDE / 'CLAUDE.local.md'
    if local_md.exists():
        try:
            texts["local:learnings"] = local_md.read_text(encoding='utf-8')
        except Exception:
            pass

    return texts


def detect_cross_domain_patterns(texts):
    """Find phrases/concepts that appear across unrelated domains."""
    # Extract key phrases (3-5 words) from each text
    domain_phrases = defaultdict(set)
    all_phrases = Counter()

    for source, text in texts.items():
        domain = source.split(':')[0]
        # Extract meaningful phrases
        words = re.findall(r'\b[a-zA-Z一-鿿]{2,}\b', text.lower())
        for i in range(len(words) - 2):
            phrase = ' '.join(words[i:i+3])
            if len(phrase) > 10:  # Minimum meaningful length
                domain_phrases[domain].add(phrase)
                all_phrases[phrase] += 1

    # Find phrases that appear in 3+ different domains
    cross_domain = []
    for phrase, count in all_phrases.items():
        domains = [d for d, phrases in domain_phrases.items() if phrase in phrases]
        if len(domains) >= 3 and count >= 3:
            cross_domain.append({
                "phrase": phrase,
                "count": count,
                "domains": domains,
                "score": len(domains) * count,
            })

    cross_domain.sort(key=lambda x: -x['score'])
    return cross_domain[:10]


# ═══════════════════════════════════════════
# DETECTOR 2: Anomaly & Friction Detector
# ═══════════════════════════════════════════

def detect_anomalies():
    """Detect anomalous patterns: unusual error rates, hook timeouts, friction clusters."""
    anomalies = []

    # Check friction events
    friction_file = EVENTS_DIR / 'friction_events.jsonl'
    if friction_file.exists():
        try:
            events = []
            for line in friction_file.read_text(encoding='utf-8').strip().split('\n'):
                if line.strip():
                    events.append(json.loads(line))

            # Group by type
            by_type = defaultdict(list)
            for e in events:
                by_type[e.get('type', 'unknown')].append(e)

            # Anomaly: same friction type in last 24h
            recent = datetime.now() - timedelta(hours=24)
            for ftype, group in by_type.items():
                recent_events = [e for e in group if e.get('timestamp', '') > recent.isoformat()]
                if len(recent_events) >= 3:
                    anomalies.append({
                        "type": "friction_cluster",
                        "detail": f"{ftype}: {len(recent_events)} events in 24h",
                        "severity": "high" if len(recent_events) >= 5 else "medium",
                    })
        except Exception:
            pass

    # Check hook performance anomalies (fixed: *.jsonl, line-by-line JSONL parse)
    perf_dir = CLAUDE / '.claude' / 'hook_perf'
    if perf_dir.exists():
        timeout_hooks = []
        for pf in perf_dir.glob("*.jsonl"):
            try:
                last_runs = []
                for line in pf.read_text(encoding='utf-8', errors='replace').strip().split('\n'):
                    if line.strip():
                        try: last_runs.append(json.loads(line))
                        except json.JSONDecodeError: pass
                for run in last_runs[-10:]:  # Last 10 runs
                    if run.get('d', 0) > 5000:  # >5s (field is 'd' not 'duration_ms')
                        timeout_hooks.append(pf.stem)
            except Exception:
                pass
        if len(timeout_hooks) >= 3:
            anomalies.append({
                "type": "hook_timeout",
                "detail": f"{len(set(timeout_hooks))} hooks exceeding 5s: {', '.join(set(timeout_hooks))}",
                "severity": "medium",
            })

    return anomalies


# ═══════════════════════════════════════════
# DETECTOR 3: Memory Decay Forecaster
# ═══════════════════════════════════════════

def forecast_memory_decay():
    """Predict which memories will become stale in the next 7/30 days."""
    if not MEMORY_DIR.exists():
        return []

    forecasts = []
    now = datetime.now()

    for mf in MEMORY_DIR.rglob("*.md"):
        if mf.name == "MEMORY.md" or '_archive' in str(mf) or 'distilled' not in str(mf.parent):
            # Skip non-memory files but include distilled
            if 'distilled' not in str(mf):
                if mf.parent.name not in ('root', 'branch', 'leaf', 'distilled'):
                    continue

        try:
            content = mf.read_text(encoding='utf-8')
            created_match = re.search(r'created:\s*(\S+)', content)
            if not created_match:
                continue
            created = datetime.fromisoformat(created_match.group(1).strip())
            days_old = (now - created).days

            # Forecast decay
            decay_7d = pow(2.71828, -(days_old + 7) / 30)
            decay_30d = pow(2.71828, -(days_old + 30) / 30)

            name_match = re.search(r'name:\s*(\S+)', content)
            name = name_match.group(1).strip() if name_match else mf.stem

            if decay_30d < 0.5:
                forecasts.append({
                    "file": str(mf.relative_to(MEMORY_DIR)),
                    "name": name,
                    "days_old": days_old,
                    "score_now": round(pow(2.71828, -days_old / 30), 2),
                    "score_7d": round(decay_7d, 2),
                    "score_30d": round(decay_30d, 2),
                    "action": "review" if decay_30d < 0.3 else "monitor",
                })
        except Exception:
            pass

    forecasts.sort(key=lambda x: x['score_30d'])
    return forecasts[:10]


# ═══════════════════════════════════════════
# DETECTOR 4: Gap Detector (Rule/Memory coverage)
# ═══════════════════════════════════════════

def detect_rule_gaps():
    """Detect missing rule coverage by analyzing error patterns."""
    gaps = []

    # Check if error types in memory have corresponding rules
    error_patterns = set()
    rule_coverage = set()

    if MEMORY_DIR.exists():
        for mf in MEMORY_DIR.rglob("*.md"):
            if mf.name == "MEMORY.md":
                continue
            try:
                content = mf.read_text(encoding='utf-8')
                mtype = re.search(r'type:\s*(\S+)', content)
                if mtype and mtype.group(1) == 'error':
                    # Extract error pattern
                    err_match = re.search(r'## Error\n```\n(.+?)\n```', content, re.DOTALL)
                    if err_match:
                        error_patterns.add(err_match.group(1).strip()[:100])
            except Exception:
                pass

    if RULES_DIR.exists():
        for rf in RULES_DIR.glob("*.md"):
            try:
                content = rf.read_text(encoding='utf-8')
                # Extract what this rule covers
                for line in content.split('\n'):
                    if line.startswith('##') or line.startswith('#'):
                        rule_coverage.add(line.strip('# ').lower())
            except Exception:
                pass

    # Gaps: errors without rule coverage
    for err in error_patterns:
        covered = any(rc in err.lower() or err.lower() in rc for rc in rule_coverage)
        if not covered:
            gaps.append({
                "type": "uncovered_error",
                "error_pattern": err[:120],
                "suggestion": f"Consider adding a rule for: {err[:80]}",
            })

    return gaps[:5]


# ═══════════════════════════════════════════
# DETECTOR 5: Association Engine (Dream Mode)
# ═══════════════════════════════════════════

def dream_associations():
    """Creative recombination: connect unrelated memories to generate novel ideas."""
    if not MEMORY_DIR.exists():
        return []

    # Load all memories as structured items
    memories = []
    for mf in MEMORY_DIR.rglob("*.md"):
        if mf.name == "MEMORY.md" or '_archive' in str(mf):
            continue
        try:
            content = mf.read_text(encoding='utf-8')
            desc = re.search(r'description:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            mtype = re.search(r'type:\s*(\S+)', content)
            domain = re.search(r'domain:\s*(\S+)', content)
            memories.append({
                "file": str(mf.relative_to(MEMORY_DIR)),
                "description": desc.group(1).strip('"') if desc else mf.stem,
                "type": mtype.group(1) if mtype else 'unknown',
                "domain": domain.group(1) if domain else 'unknown',
            })
        except Exception:
            pass

    if len(memories) < 3:
        return []

    # Randomly combine unrelated memories and generate "what if" connections
    associations = []
    seen_pairs = set()

    # Sort by type to favor cross-type associations
    for _ in range(min(15, len(memories) * 2)):
        m1, m2 = random.sample(memories, 2)
        pair_key = tuple(sorted([m1['file'], m2['file']]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # Only connect memories of different types for more interesting associations
        if m1['type'] == m2['type'] and m1['domain'] == m2['domain']:
            continue

        # Generate associative connection
        connection = f"What if we apply '{m1['description'][:60]}' ({m1['type']}) to '{m2['description'][:60]}' ({m2['type']})?"
        associations.append({
            "mem1": m1['description'][:80],
            "mem2": m2['description'][:80],
            "connection": connection,
            "domains": f"{m1['domain']} × {m2['domain']}",
        })

    return associations[:8]


# ═══════════════════════════════════════════
# DETECTOR 6: Growth Tracker
# ═══════════════════════════════════════════

def track_growth():
    """Track system growth over time: tools, rules, memories, capabilities."""
    now = datetime.now()

    metrics = {
        "tools": len(list(SCRIPTS_DIR.glob("*.py"))) if SCRIPTS_DIR.exists() else 0,
        "rules": len(list(RULES_DIR.glob("*.md"))) if RULES_DIR.exists() else 0,
        "hooks": len(list((SCRIPTS_DIR / 'hooks').glob("*.ps1"))) if (SCRIPTS_DIR / 'hooks').exists() else 0,
        "memories": len(list(MEMORY_DIR.rglob("*.md"))) - 1 if MEMORY_DIR.exists() else 0,  # -1 for MEMORY.md
    }

    # Compare with historical baseline
    baseline_file = BLACKBOARD / '_growth_baseline.json'
    baseline = {}
    if baseline_file.exists():
        try:
            baseline = json.loads(baseline_file.read_text(encoding='utf-8'))
        except Exception:
            pass

    changes = {}
    for key, value in metrics.items():
        old = baseline.get(key, value)
        if old != value:
            changes[key] = {"from": old, "to": value, "delta": value - old}

    # Save new baseline
    baseline_file.write_text(json.dumps({**metrics, "updated": now.isoformat()}, ensure_ascii=False, indent=2))

    return {"current": metrics, "changes": changes}


# ═══════════════════════════════════════════
# MAIN ORCHESTRATION
# ═══════════════════════════════════════════

def run_all_detectors(mode="normal"):
    """Run all subconscious detectors and generate insight cards."""
    cards = []
    now = datetime.now()

    # ── Pattern Detection (always runs) ──
    texts = load_all_texts()
    cross_patterns = detect_cross_domain_patterns(texts)
    if cross_patterns:
        patterns_text = "\n".join(
            f"- '{p['phrase']}' appears in {len(p['domains'])} domains ({', '.join(p['domains'])}) — {p['count']} occurrences"
            for p in cross_patterns[:5]
        )
        cards.append(write_card(
            "pattern", "Cross-domain patterns detected",
            patterns_text, 0.6,
            [p['phrase'] for p in cross_patterns[:3]],
            tags=["pattern", "cross-domain"]
        ))

    # ── Anomaly Detection ──
    anomalies = detect_anomalies()
    if anomalies:
        anomaly_text = "\n".join(
            f"- [{a['severity'].upper()}] {a['detail']}"
            for a in anomalies
        )
        cards.append(write_card(
            "anomaly", f"{len(anomalies)} anomalies detected",
            anomaly_text, 0.7 if any(a['severity'] == 'high' for a in anomalies) else 0.5,
            [a['type'] for a in anomalies],
            tags=["anomaly", "alert"]
        ))

    # ── Memory Decay Forecast ──
    forecasts = forecast_memory_decay()
    urgent = [f for f in forecasts if f['action'] == 'review']
    if urgent:
        forecast_text = "\n".join(
            f"- [{f['score_30d']:.2f}] {f['name']} (now {f['score_now']:.2f}, {f['days_old']}d old)"
            for f in urgent[:5]
        )
        cards.append(write_card(
            "forecast", f"{len(urgent)} memories need review within 30 days",
            forecast_text, 0.55,
            [f['name'] for f in urgent[:3]],
            tags=["memory", "decay", "forecast"]
        ))

    # ── Rule Gap Detection ──
    gaps = detect_rule_gaps()
    if gaps:
        gap_text = "\n".join(
            f"- {g['suggestion']}"
            for g in gaps
        )
        cards.append(write_card(
            "gap", f"{len(gaps)} rule coverage gaps found",
            gap_text, 0.5,
            [g['error_pattern'][:60] for g in gaps],
            tags=["rule", "gap", "improvement"]
        ))

    # ── Growth Tracking ──
    growth = track_growth()
    if growth['changes']:
        growth_text = "\n".join(
            f"- {k}: {v['from']} → {v['to']} ({'+' if v['delta'] > 0 else ''}{v['delta']})"
            for k, v in growth['changes'].items()
        )
        cards.append(write_card(
            "growth", "System growth detected",
            growth_text, 0.9,
            [k for k in growth['changes']],
            tags=["growth", "metrics"]
        ))

    # ── Dream Mode: Creative Associations ──
    if mode == "dream":
        associations = dream_associations()
        if associations:
            dream_text = "\n".join(
                f"- 💭 {a['connection']} [{a['domains']}]"
                for a in associations[:5]
            )
            cards.append(write_card(
                "dream", f"Dream: {len(associations)} creative associations",
                dream_text, 0.3,  # Low confidence — these are creative leaps
                [a['connection'][:60] for a in associations[:3]],
                tags=["dream", "creative", "association"]
            ))

    # ── Summary ──
    card_types = Counter(c['type'] for c in cards)
    write_card(
        "summary", f"Subconscious cycle: {len(cards)} insights",
        f"Types: {dict(card_types)}\n"
        f"Total unacknowledged cards: {len(read_blackboard())}\n"
        f"Mode: {mode}\n"
        f"Timestamp: {now.isoformat()}",
        0.95,
        [],
        tags=["meta", "summary"]
    )

    return cards


def inject_context(cards, max_tokens=250):
    """Generate compact context block from subconscious insights."""
    if not cards:
        return ""

    type_icons = {
        "pattern": "🔍", "anomaly": "⚠️", "forecast": "📉", "gap": "🕳️",
        "growth": "📈", "dream": "💭", "summary": "📋"
    }

    lines = ["## Subconscious Insights (auto-detected)"]
    token_est = 20

    for card in cards:
        icon = type_icons.get(card['type'], '💡')
        title = card['title'][:100]
        line = f"- {icon} [{card['type']}] {title} ({card['confidence']:.0%})"
        line_tokens = len(line) // 3
        if token_est + line_tokens > max_tokens:
            break
        lines.append(line)
        token_est += line_tokens

        # Add detail for top 3
        if len(lines) <= 4:
            body = card['body'][:150].replace('\n', ' | ')
            snippet = f"  {body}"
            snip_tokens = len(snippet) // 3
            if token_est + snip_tokens <= max_tokens:
                lines.append(snippet)
                token_est += snip_tokens

    return '\n'.join(lines)


def main():
    mode = "normal"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]
    elif "--dream" in sys.argv:
        mode = "dream"

    use_json = "--json" in sys.argv
    do_inject = "--inject" in sys.argv

    if mode == "dream":
        # Force dream mode
        cards = run_all_detectors("dream")
    else:
        cards = run_all_detectors(mode)

    if do_inject:
        print(inject_context(read_blackboard()))
        return

    if use_json:
        output = []
        for c in cards:
            output.append({
                "id": c['id'], "type": c['type'], "title": c['title'],
                "confidence": c['confidence'], "tags": c['tags'],
            })
        print(json.dumps({"cards": len(cards), "total_unacknowledged": len(read_blackboard()), "insights": output},
                        ensure_ascii=False, indent=2))
    else:
        print(f"🧠 SUBCONSCIOUS: {mode} mode — {len(cards)} insights surfaced")
        for card in cards:
            icon = {"pattern": "🔍", "anomaly": "⚠️", "forecast": "📉", "gap": "🕳️",
                    "growth": "📈", "dream": "💭", "summary": "📋"}.get(card['type'], '💡')
            print(f"  {icon} [{card['type']}] {card['title']} ({card['confidence']:.0%})")
            body_preview = card['body'][:200].replace('\n', '\n     ')
            print(f"     {body_preview}")

if __name__ == "__main__":
    main()
