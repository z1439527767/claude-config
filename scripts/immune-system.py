#!/usr/bin/env python3
"""immune-system — Ralph's proactive defense layer.
Like the body's immune system: recognizes pathogens, deploys white blood cells,
builds antibodies, quarantines threats, maintains immune memory.

Three layers:
  L1: Innate Immunity    — Pre-execution safety checks (always active)
  L2: Adaptive Immunity  — Pattern-based threat detection (learns over time)
  L3: Immune Memory      — Vaccination records (never let the same bug infect twice)

Usage:
  python3 immune-system.py --check <operation>    # Pre-flight safety check
  python3 immune-system.py --scan                  # Full system scan (white blood cells)
  python3 immune-system.py --vaccinate <pattern>   # Record a known threat
  python3 immune-system.py --status               # Immune system health
  python3 immune-system.py --inject               # Safety brief for SessionStart
"""
import sys, json, os, io, re, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
try: from db import write_log
except ImportError: write_log = lambda s,k,d: None

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
IMMUNE_DIR = CLAUDE / '.claude' / 'immune'
IMMUNE_DIR.mkdir(parents=True, exist_ok=True)

VACCINES_FILE = IMMUNE_DIR / 'vaccines.json'
THREAT_LOG = IMMUNE_DIR / 'threat_log.jsonl'
SCAN_STATE = IMMUNE_DIR / 'scan_state.json'

# ═══════════════════════════════════════════
# L1: INNATE IMMUNITY — Always-active safety checks
# ═══════════════════════════════════════════

INNATE_RULES = [
    {
        "id": "no-force-default-branch",
        "pattern": r"git\s+(push|reset).*(--force|--hard).*(main|master)",
        "severity": "critical",
        "action": "block",
        "message": "Never force-push or hard-reset the default branch.",
    },
    {
        "id": "no-skip-hooks",
        "pattern": r"--no-verify|--no-gpg-sign|-c\s+commit\.gpgsign=false",
        "severity": "high",
        "action": "warn",
        "message": "Skipping git hooks. Only do this if a hook is broken and needs fixing.",
    },
    {
        "id": "no-secret-exposure",
        "pattern": r"(sk-[a-zA-Z0-9]{20,}|API[_-]?KEY\s*=\s*[a-zA-Z0-9]{10,}|token\s*=\s*[a-zA-Z0-9_-]{20,})",
        "severity": "critical",
        "action": "block",
        "message": "Potential secret exposure detected. Never output secrets to terminal or files.",
    },
    {
        "id": "no-delete-git",
        "pattern": r"rm\s+.*-rf\s+.*\.git",
        "severity": "critical",
        "action": "block",
        "message": "Attempting to delete .git directory. This is irreversible.",
    },
    {
        "id": "no-dangerous-redirect",
        "pattern": r">\s*/dev/[a-z]+\d|>\s*/etc/|>\s*/proc/",
        "severity": "high",
        "action": "warn",
        "message": "Writing to system files. Verify this is intentional.",
    },
    {
        "id": "no-rm-star",
        "pattern": r"rm\s+.*-rf\s+\*|rm\s+.*-rf\s+~/",
        "severity": "critical",
        "action": "block",
        "message": "Dangerous recursive remove detected. Verify the path.",
    },
    {
        "id": "no-curl-bash",
        "pattern": r"curl\s+.*\|\s*(bash|sh|zsh)",
        "severity": "high",
        "action": "warn",
        "message": "curl | bash pattern. Always inspect downloaded scripts before executing.",
    },
    {
        "id": "no-npm-audit-fix-force",
        "pattern": r"npm\s+audit\s+fix\s+--force",
        "severity": "medium",
        "action": "warn",
        "message": "npm audit fix --force can break dependencies. Use without --force first.",
    },
]

def innate_check(command):
    """Run innate immunity checks on a command. Returns (safe, warnings, blocks)."""
    warnings = []
    blocks = []

    for rule in INNATE_RULES:
        if re.search(rule["pattern"], command, re.IGNORECASE):
            if rule["action"] == "block":
                blocks.append(rule)
            else:
                warnings.append(rule)

    safe = len(blocks) == 0
    return safe, warnings, blocks


# ═══════════════════════════════════════════
# L2: ADAPTIVE IMMUNITY — Learned threat patterns
# ═══════════════════════════════════════════

def load_vaccines():
    """Load known threat patterns (vaccination records)."""
    if VACCINES_FILE.exists():
        try:
            return json.loads(VACCINES_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"vaccines": [], "last_updated": None}

def save_vaccines(vaccines):
    vaccines["last_updated"] = datetime.now().isoformat()
    VACCINES_FILE.write_text(json.dumps(vaccines, ensure_ascii=False, indent=2), encoding='utf-8')

def vaccinate(pattern, fix, severity="medium", source=""):
    """Record a new threat pattern — build an antibody."""
    vaccines = load_vaccines()
    vac_id = hashlib.sha256(pattern.encode()).hexdigest()[:12]
    vaccine = {
        "id": vac_id,
        "pattern": pattern,
        "fix": fix,
        "severity": severity,
        "source": source,
        "created": datetime.now().isoformat(),
        "hit_count": 0,
    }
    # Check for duplicates
    existing = [v for v in vaccines["vaccines"] if v["pattern"] == pattern]
    if existing:
        existing[0]["hit_count"] += 1
    else:
        vaccines["vaccines"].append(vaccine)
    save_vaccines(vaccines)
    return vac_id

def adaptive_check(context):
    """Check context against learned threat patterns."""
    vaccines = load_vaccines()
    matches = []

    for v in vaccines["vaccines"]:
        try:
            if re.search(v["pattern"], context, re.IGNORECASE):
                matches.append(v)
        except re.error:
            pass

    return matches

def log_threat(threat_type, detail, severity="medium", handled=True):
    """Log a threat encounter."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": threat_type,
        "detail": detail[:500],
        "severity": severity,
        "handled": handled,
    }
    with open(THREAT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    try: write_log("threat_log", None, entry)
    except Exception: pass


# ═══════════════════════════════════════════
# L3: SYSTEM SCAN — White blood cell patrol
# ═══════════════════════════════════════════

def scan_system():
    """Full system security scan."""
    findings = []

    # 1. Check for hardcoded secrets in config files
    secret_patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', "API key"),
        (r'[A-Za-z0-9+/]{40,}={0,2}', "Potential base64 secret"),
    ]
    config_files = [
        CLAUDE / 'settings.json',
        CLAUDE / 'CLAUDE.local.md',
        CLAUDE / '.claude' / 'rules' / 'security.md',
    ]
    for cf in config_files:
        if cf.exists():
            try:
                content = cf.read_text(encoding='utf-8')
                for pat, desc in secret_patterns:
                    matches = re.findall(pat, content)
                    if matches:
                        findings.append({
                            "level": "critical",
                            "file": str(cf.relative_to(HOME)),
                            "issue": f"Potential {desc} found",
                            "count": len(matches),
                        })
            except Exception:
                pass

    # 2. Check hook security
    hooks_dir = CLAUDE / 'scripts' / 'hooks'
    if hooks_dir.exists():
        for hf in hooks_dir.glob("*.ps1"):
            try:
                content = hf.read_text(encoding='utf-8')
                # Check exit codes: security hooks must exit 2 on deny
                # Only flag if deny/permissionDecision is on a nearby line before exit 0
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'deny' in line.lower() and 'permissionDecision' in line:
                        # Check next 3 lines for exit 0
                        nearby = '\n'.join(lines[i:min(i+4, len(lines))])
                        if 'exit 0' in nearby and 'exit 2' not in nearby:
                            findings.append({
                                "level": "high",
                                "file": str(hf.relative_to(HOME)),
                                "issue": "Security hook exits 0 on deny (should exit 2)",
                            })
                            break
            except Exception:
                pass

    # 3. Check for stale lock files
    lock_dir = CLAUDE / '.claude'
    for lf in lock_dir.glob("*.lock"):
        age = datetime.now() - datetime.fromtimestamp(lf.stat().st_mtime)
        if age > timedelta(hours=1):
            findings.append({
                "level": "low",
                "file": str(lf.relative_to(HOME)),
                "issue": f"Stale lock file ({age.total_seconds()/3600:.1f}h old)",
            })

    return findings


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def immune_status():
    """Get immune system health status."""
    vaccines = load_vaccines()
    threat_count = 0
    if THREAT_LOG.exists():
        threat_count = sum(1 for _ in open(THREAT_LOG, 'r', encoding='utf-8'))

    # Recent threats
    recent_threats = []
    if THREAT_LOG.exists():
        cutoff = datetime.now() - timedelta(hours=24)
        for line in open(THREAT_LOG, 'r', encoding='utf-8'):
            try:
                t = json.loads(line)
                if datetime.fromisoformat(t["timestamp"]) > cutoff:
                    recent_threats.append(t)
            except Exception:
                pass

    return {
        "vaccines": len(vaccines.get("vaccines", [])),
        "innate_rules": len(INNATE_RULES),
        "total_threats_logged": threat_count,
        "recent_threats_24h": len(recent_threats),
        "last_scan": None,
        "status": "healthy" if len(recent_threats) < 5 else "elevated",
    }


def main():
    if "--check" in sys.argv:
        idx = sys.argv.index("--check")
        if idx + 1 < len(sys.argv):
            cmd = sys.argv[idx + 1]
            safe, warnings, blocks = innate_check(cmd)
            # Also check adaptive
            adaptive_matches = adaptive_check(cmd)

            result = {
                "safe": safe and len(adaptive_matches) == 0,
                "warnings": [w["message"] for w in warnings],
                "blocks": [b["message"] for b in blocks],
                "adaptive_matches": [a["fix"] for a in adaptive_matches],
            }
            if "--json" in sys.argv:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                if result["safe"]:
                    print("IMMUNE: ✅ Safe")
                else:
                    print("IMMUNE: 🔴 BLOCKED")
                    for b in result["blocks"]:
                        print(f"  🚫 {b}")
                for w in result["warnings"]:
                    print(f"  ⚠️  {w}")
                for a in result["adaptive_matches"]:
                    print(f"  🛡️  {a}")
            return

    if "--scan" in sys.argv:
        findings = scan_system()
        if not findings:
            print("IMMUNE SCAN: ✅ No threats found")
        else:
            print(f"IMMUNE SCAN: {len(findings)} issues found")
            for f in findings:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(f["level"], "⚪")
                print(f"  {icon} [{f['level']}] {f.get('file', '?')}: {f['issue']}")
        return

    if "--vaccinate" in sys.argv:
        idx = sys.argv.index("--vaccinate")
        if idx + 1 < len(sys.argv):
            pattern = sys.argv[idx + 1]
            fix = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else "See pattern"
            vid = vaccinate(pattern, fix)
            print(f"IMMUNE: Vaccinated — antibody {vid}")
        return

    if "--status" in sys.argv:
        status = immune_status()
        if "--json" in sys.argv:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print(f"IMMUNE SYSTEM STATUS: {status['status']}")
            print(f"  💉 {status['vaccines']} vaccines | 🛡️ {status['innate_rules']} innate rules")
            print(f"  📋 {status['total_threats_logged']} threats logged ({status['recent_threats_24h']} in last 24h)")
        return

    if "--inject" in sys.argv:
        status = immune_status()
        print(f"## Immune System: {status['status']}")
        print(f"- {status['vaccines']} known threat patterns vaccinated")
        print(f"- {status['innate_rules']} innate safety rules active")
        if status['recent_threats_24h'] > 0:
            print(f"- ⚠️ {status['recent_threats_24h']} threats in last 24h — elevated vigilance")
        return

    # Default
    print("immune-system: --check <cmd> | --scan | --vaccinate <pattern> <fix> | --status | --inject")

if __name__ == "__main__":
    main()
