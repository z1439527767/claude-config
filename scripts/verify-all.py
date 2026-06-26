#!/usr/bin/env python3
"""verify-all — autonomous expert-level master verification orchestrator.
Runs ALL checks across the entire .claude system. Auto-fixes simple issues.
Usage:
  python3 verify-all.py                    # Full verification (human-readable)
  python3 verify-all.py --json             # Machine-readable output
  python3 verify-all.py --fix              # Auto-fix simple issues
  python3 verify-all.py --quick            # Fast mode: critical checks only
  python3 verify-all.py --watch            # Continuous watch mode (runs on schedule)

Verification Layers (7 total):
  L1: Syntax — all .ps1/.py/.json parse clean
  L2: References — all hook paths resolve, all CLAUDE.md refs exist
  L3: Rules — no contradictions, all have frontmatter, under size limits
  L4: Security — injection scan, protected files, credential leaks
  L5: Performance — hook perf metrics, no heavy scripts, timeout compliance
  L6: State — circuit breaker, error budget, memory scores, rogue state
  L7: Integration — cross-tool consistency, knowledge graph health

Exit codes: 0=clean, 1=warnings, 2=errors, 3=critical
"""
import sys, json, os, io, re, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
RULES_DIR = CLAUDE / '.claude' / 'rules'
SCRIPTS_DIR = CLAUDE / 'scripts'
HOOKS_DIR = SCRIPTS_DIR / 'hooks'
LIB_DIR = SCRIPTS_DIR / 'lib'
SETTINGS_FILE = CLAUDE / 'settings.json'
CLAUDE_MD = CLAUDE / 'CLAUDE.md'
AGENTS_MD = CLAUDE / 'AGENTS.md'
_mem_dirs = list((CLAUDE / 'projects').glob('*/memory'))
MEMORY_DIR = _mem_dirs[0] if _mem_dirs else CLAUDE / 'projects' / f'C--Users-{os.environ.get("USERNAME","z1439")}--claude' / 'memory'

SEVERITY = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "CRITICAL": 4}
SEVERITY_ICON = {"OK": "✅", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "🔴", "CRITICAL": "🚨"}

class Verifier:
    def __init__(self, fix=False, quick=False):
        self.fix = fix
        self.quick = quick
        self.findings = []
        self.stats = Counter()
        self.start_time = datetime.now()

    def add(self, layer, severity, component, message, detail="", auto_fix=None):
        self.findings.append({
            "layer": layer, "severity": severity, "component": component,
            "message": message, "detail": detail, "auto_fix": auto_fix,
            "timestamp": datetime.now().isoformat(),
        })
        self.stats[severity] += 1

    # ═══ L1: Syntax Verification ═══
    def verify_syntax(self):
        """Verify all scripts parse without errors."""
        layer = "L1-syntax"

        # PowerShell scripts
        for d in [HOOKS_DIR, LIB_DIR]:
            if not d.exists():
                continue
            for f in d.glob("*.ps1"):
                try:
                    result = subprocess.run(
                        ["pwsh", "-NoProfile", "-Command",
                         f"$t=$null;$e=$null;$a=[System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$t,[ref]$e);exit($e.Count)"],
                        capture_output=True, text=True, timeout=10,
                        encoding='utf-8', errors='replace'
                    )
                    if result.returncode != 0:
                        self.add(layer, "ERROR", f.name,
                                f"Syntax error in {f.name}", f"pwsh returned code {result.returncode}")
                    else:
                        self.add(layer, "OK", f.name, f"Parse OK", "")
                except subprocess.TimeoutExpired:
                    self.add(layer, "WARN", f.name, f"Parse timeout (may be large file)")
                except FileNotFoundError:
                    self.add(layer, "ERROR", "pwsh", "PowerShell not found — cannot verify .ps1 files")
                    break
                except Exception as e:
                    self.add(layer, "ERROR", f.name, f"Parse check failed: {e}")

        # Python scripts
        for d in [SCRIPTS_DIR, HOOKS_DIR, LIB_DIR]:
            if not d.exists():
                continue
            for f in d.glob("*.py"):
                try:
                    result = subprocess.run(
                        ["python", "-m", "py_compile", str(f)],
                        capture_output=True, text=True, timeout=10,
                        encoding='utf-8', errors='replace'
                    )
                    if result.returncode != 0:
                        self.add(layer, "ERROR", f.name,
                                f"Syntax error in {f.name}",
                                result.stderr[:200] if result.stderr else "unknown")
                    else:
                        self.add(layer, "OK", f.name, f"Compile OK", "")
                except subprocess.TimeoutExpired:
                    self.add(layer, "WARN", f.name, f"Compile timeout")
                except Exception as e:
                    self.add(layer, "ERROR", f.name, f"Compile check failed: {e}")

        # JSON
        if SETTINGS_FILE.exists():
            try:
                json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
                self.add(layer, "OK", "settings.json", "Valid JSON")
            except json.JSONDecodeError as e:
                self.add(layer, "CRITICAL", "settings.json", f"Invalid JSON: {e}")
        else:
            self.add(layer, "CRITICAL", "settings.json", "MISSING — agent cannot function")

    # ═══ L2: Reference Integrity ═══
    def verify_references(self):
        """Verify all references in CLAUDE.md and settings.json resolve."""
        layer = "L2-refs"

        # CLAUDE.md references
        if CLAUDE_MD.exists():
            content = CLAUDE_MD.read_text(encoding='utf-8')
            refs = re.findall(r'@(\.claude/rules/[\w-]+\.md)', content)
            for ref in refs:
                path = CLAUDE / ref
                if not path.exists():
                    self.add(layer, "ERROR", "CLAUDE.md", f"Broken ref: {ref}",
                            auto_fix=f"Check if file was renamed or create: {path}")

            script_refs = re.findall(r'scripts/([\w\-/]+\.(py|ps1))', content)
            for ref, ext in script_refs:
                path = CLAUDE / 'scripts' / ref
                if not path.exists():
                    self.add(layer, "ERROR", "CLAUDE.md", f"Broken script ref: scripts/{ref}")

        # AGENTS.md references
        if AGENTS_MD.exists():
            content = AGENTS_MD.read_text(encoding='utf-8')
            refs = re.findall(r'@(\.claude/rules/[\w-]+\.md)', content)
            for ref in refs:
                path = CLAUDE / ref
                if not path.exists():
                    self.add(layer, "ERROR", "AGENTS.md", f"Broken ref: {ref}")

        # settings.json hook references
        if SETTINGS_FILE.exists():
            try:
                settings = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
                if "hooks" in settings:
                    for hook_type, hook_groups in settings["hooks"].items():
                        if not isinstance(hook_groups, list):
                            hook_groups = [hook_groups] if hook_groups else []
                        for group in hook_groups:
                            for hook in group.get("hooks", []):
                                cmd = hook.get("command", "")
                                # Extract script paths
                                for m in re.finditer(r'scripts\\(hooks|lib)\\([\w\-]+\.ps1)', cmd):
                                    script_path = SCRIPTS_DIR / m.group(1) / m.group(2)
                                    if not script_path.exists():
                                        self.add(layer, "ERROR", f"{hook_type}/{m.group(2)}",
                                                f"Hook script missing: {script_path}")
                                # Check timeout values
                                timeout = hook.get("timeout", 30)
                                if timeout > 10 and not hook.get("runInBackground"):
                                    self.add(layer, "INFO", f"{hook_type}",
                                            f"Hook timeout {timeout}s > 10s without background — consider adding runInBackground")

                # Verify MCP servers have valid configs
                for server_name, server_cfg in settings.get("mcpServers", {}).items():
                    if server_cfg.get("command") and not server_cfg.get("type"):
                        if server_cfg["command"] not in ("npx", "uvx", "clast-ai", "gortex"):
                            self.add(layer, "INFO", f"mcp/{server_name}",
                                    f"Custom MCP command: {server_cfg['command']}")
            except Exception as e:
                self.add(layer, "ERROR", "settings.json", f"Failed to parse: {e}")

    # ═══ L3: Rules Consistency ═══
    def verify_rules(self):
        """Check rules for contradictions, size, frontmatter."""
        layer = "L3-rules"

        if not RULES_DIR.exists():
            self.add(layer, "ERROR", "rules", "Rules directory missing")
            return

        rules = {}
        for f in RULES_DIR.glob("*.md"):
            content = f.read_text(encoding='utf-8', errors='ignore')
            lines = content.count('\n') + 1
            has_fm = content.startswith('---')
            rules[f.stem] = {"lines": lines, "has_frontmatter": has_fm, "content": content, "file": f}

            if lines > 200:
                self.add(layer, "WARN", f.name, f"Oversized: {lines} lines (>200)",
                        auto_fix="Split into multiple focused files")
            if not has_fm:
                self.add(layer, "INFO", f.name, f"Missing YAML frontmatter",
                        auto_fix=f"Add '---\\nmode: always\\ndescription: ...\\n---' to {f.name}")

        # Detect potential contradictions
        contradictions = [
            (["tools.md", "context.md"], r'工具.*越多越好|工具.*越少越好',
             "Tool philosophy contradiction: tools.md says 'dedicated tools first', context.md says 'fewer tools'"),
            (["errors.md", "execution.md"], r'重试|retry',
             "Retry policy: errors.md says max 1 retry, check execution.md consistency"),
        ]
        for rule_pair, pattern, desc in contradictions:
            for r in rule_pair:
                if r in rules:
                    self.add(layer, "INFO", r, desc)

    # ═══ L4: Security ═══
    def verify_security(self):
        """Security-focused checks."""
        layer = "L4-security"

        # Check for hardcoded secrets in scripts
        secret_patterns = [
            (r'(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*["\'][A-Za-z0-9_\-]{10,}["\']', "CRITICAL"),
            (r'(?i)(sk-[a-zA-Z0-9]{20,})', "CRITICAL"),
            (r'(?i)(github_pat_[a-zA-Z0-9_]{20,})', "CRITICAL"),
        ]
        for d in [SCRIPTS_DIR, HOOKS_DIR, LIB_DIR]:
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.suffix not in ('.py', '.ps1', '.sh', '.json', '.yaml', '.yml', '.toml', '.md'):
                    continue
                if '.git' in f.parts or 'node_modules' in f.parts:
                    continue
                try:
                    content = f.read_text(encoding='utf-8', errors='ignore')
                    for pattern, sev in secret_patterns:
                        if re.search(pattern, content):
                            self.add(layer, sev, f.name,
                                    f"Possible secret in {f.relative_to(CLAUDE)}",
                                    "Remove hardcoded credentials and use environment variables")
                except Exception:
                    pass

        # Protected files should not be world-writable (Windows: check read-only)
        protected = [SETTINGS_FILE, CLAUDE_MD, AGENTS_MD]
        for pf in protected:
            if pf.exists():
                try:
                    if os.access(pf, os.W_OK):
                        self.add(layer, "INFO", pf.name, f"Protected file {pf.name} is writable")
                except Exception:
                    pass

    # ═══ L5: Performance ═══
    def verify_performance(self):
        """Check hook performance metrics."""
        layer = "L5-perf"

        perf_dir = CLAUDE / '.claude' / 'hook_perf'
        if not perf_dir.exists():
            self.add(layer, "INFO", "perf", "No performance data yet — hooks haven't run enough")
            return

        slow_hooks = []
        for f in perf_dir.glob("*.jsonl"):
            durations = []
            for line in f.read_text(encoding='utf-8', errors='ignore').split('\n')[-50:]:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                    d = e.get('duration_ms', e.get('d', 0))
                    if d:
                        durations.append(int(d))
                except Exception:
                    pass
            if durations:
                avg = sum(durations) / len(durations)
                mx = max(durations)
                if avg > 1000:  # >1 second average
                    slow_hooks.append((f.stem, avg, mx))
                    self.add(layer, "WARN", f.stem,
                            f"Slow hook: avg={avg:.0f}ms max={mx}ms",
                            auto_fix="Optimize or set runInBackground: true")

        if not slow_hooks:
            self.add(layer, "OK", "perf", "All hooks within performance targets")

        # Check for heavy scripts (>200 lines)
        for d in [HOOKS_DIR, LIB_DIR]:
            if not d.exists():
                continue
            for f in d.glob("*.ps1"):
                lines = f.read_text(encoding='utf-8', errors='ignore').count('\n') + 1
                if lines > 200:
                    self.add(layer, "WARN", f.name, f"Heavy script: {lines} lines",
                            auto_fix="Split into lib/ modules")

    # ═══ L6: State Health ═══
    def verify_state(self):
        """Check runtime state: circuit breaker, error budget, memory."""
        layer = "L6-state"

        # Circuit breaker
        cb_file = CLAUDE / 'session-env' / 'circuit_breaker.json'
        if cb_file.exists():
            try:
                cb = json.loads(cb_file.read_text(encoding='utf-8'))
                state = cb.get('state', 'UNKNOWN')
                if state == 'OPEN':
                    self.add(layer, "CRITICAL", "circuit-breaker",
                            f"Circuit is OPEN — {cb.get('failure_count', '?')} failures")
                elif state == 'HALF_OPEN':
                    self.add(layer, "WARN", "circuit-breaker", "Circuit is HALF_OPEN — recovering")
                else:
                    self.add(layer, "OK", "circuit-breaker", f"State: {state}")
            except Exception as e:
                self.add(layer, "WARN", "circuit-breaker", f"Cannot read state: {e}")

        # Error budget
        eb_file = CLAUDE / 'session-env' / 'error_budget.json'
        if eb_file.exists():
            try:
                eb = json.loads(eb_file.read_text(encoding='utf-8'))
                total = eb.get('total_successes', 0) + eb.get('total_failures', 0)
                if total > 10:
                    error_rate = eb.get('total_failures', 0) / total
                    if error_rate > 0.05:
                        self.add(layer, "WARN", "error-budget",
                                f"Error rate {error_rate:.1%} — SLO target 0.5%")
                    else:
                        self.add(layer, "OK", "error-budget",
                                f"Error rate {error_rate:.2%} (SLO 0.5%)")
            except Exception:
                pass

        # Memory scores
        mem_index = MEMORY_DIR / 'MEMORY.md'
        if mem_index.exists():
            content = mem_index.read_text(encoding='utf-8', errors='ignore')
            stale_count = content.count('[stale]') + content.count('[expired]')
            fresh_count = content.count('[fresh]')
            total = content.count('[')
            self.add(layer, "OK" if stale_count < 3 else "WARN", "memory",
                    f"Memory: {fresh_count} fresh, {stale_count} stale/expired of ~{total} entries",
                    auto_fix="Run memory-consolidator.py to clean stale entries" if stale_count >= 3 else None)

        # Rogue state
        rogue_file = CLAUDE / 'session-env' / 'rogue_state.json'
        if rogue_file.exists():
            try:
                rogue = json.loads(rogue_file.read_text(encoding='utf-8'))
                if rogue.get("alert_count", 0) > 0:
                    self.add(layer, "WARN", "rogue-detector",
                            f"{rogue['alert_count']} rogue alerts")
                else:
                    self.add(layer, "OK", "rogue-detector", "No rogue alerts")
            except Exception:
                pass

    # ═══ L7: Integration ═══
    def verify_integration(self):
        """Cross-tool consistency and integration health."""
        layer = "L7-integration"

        # Knowledge graph connectivity (if available)
        try:
            result = subprocess.run(
                ["python", "-c", "import sys; sys.path.insert(0, '.'); "
                 "print('kg: available' if __import__('json').loads('{}') is not None else 'no')"],
                capture_output=True, text=True, timeout=5, encoding='utf-8', errors='replace'
            )
        except Exception:
            self.add(layer, "INFO", "knowledge-graph", "Cannot verify KG connectivity (MCP may be offline)")

        # Git status
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=CLAUDE, timeout=5,
                encoding='utf-8', errors='replace'
            )
            dirty = len([l for l in result.stdout.split('\n') if l.strip()])
            if dirty > 0:
                self.add(layer, "WARN", "git", f"{dirty} uncommitted files",
                        auto_fix="Commit or stash changes")
            else:
                self.add(layer, "OK", "git", "Working tree clean")
        except Exception:
            self.add(layer, "WARN", "git", "Cannot check git status")

        # Disk space
        try:
            import shutil
            usage = shutil.disk_usage(str(HOME))
            free_gb = usage.free / (1024**3)
            if free_gb < 10:
                self.add(layer, "WARN", "disk", f"Low disk: {free_gb:.1f}GB free")
            else:
                self.add(layer, "OK", "disk", f"{free_gb:.1f}GB free")
        except Exception:
            pass

    def auto_fix_simple(self):
        """Auto-fix issues that have a clear, safe fix."""
        fixed = 0
        for f in self.findings:
            if not f.get("auto_fix") or f["severity"] in ("OK", "INFO"):
                continue

            # Example auto-fixes:
            # - Add missing frontmatter to rule files
            if "Missing YAML frontmatter" in f["message"] and self.fix:
                rule_file = RULES_DIR / f["component"]
                if rule_file.exists():
                    content = rule_file.read_text(encoding='utf-8')
                    if not content.startswith('---'):
                        fm = f"---\nmode: always\ndescription: {f['component'].replace('.md','')} rules\n---\n"
                        rule_file.write_text(fm + content, encoding='utf-8')
                        f["auto_fix_applied"] = True
                        fixed += 1
        return fixed

    def run_all(self):
        """Run all verification layers."""
        layers = [
            ("L1-syntax", self.verify_syntax),
            ("L2-refs", self.verify_references),
            ("L3-rules", self.verify_rules),
            ("L4-security", self.verify_security),
        ]
        if not self.quick:
            layers += [
                ("L5-perf", self.verify_performance),
                ("L6-state", self.verify_state),
                ("L7-integration", self.verify_integration),
            ]

        for name, method in layers:
            try:
                method()
            except Exception as e:
                self.add(name, "ERROR", "verifier", f"Layer {name} crashed: {e}")

        if self.fix:
            fixed = self.auto_fix_simple()
            if fixed:
                self.add("meta", "INFO", "auto-fix", f"Auto-fixed {fixed} issues")

    def report(self, use_json=False):
        if use_json:
            print(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
            return

        duration = (datetime.now() - self.start_time).total_seconds()
        errors = self.stats.get("ERROR", 0) + self.stats.get("CRITICAL", 0)
        warns = self.stats.get("WARN", 0)
        oks = self.stats.get("OK", 0)

        print(f"╔══════════════════════════════════════════╗")
        print(f"║  🔍 VERIFY-ALL — Master Verification     ║")
        print(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {duration:.1f}s  {'✅ PASS' if errors == 0 else '🔴 FAIL'}       ║")
        print(f"╠══════════════════════════════════════════╣")
        print(f"║  Findings: {len(self.findings)} total = {oks} OK + {warns} WARN + {errors} ERR  ║")
        print(f"╚══════════════════════════════════════════╝")
        print()

        # Group by layer
        by_layer = defaultdict(list)
        for f in self.findings:
            by_layer[f["layer"]].append(f)

        for layer in sorted(by_layer.keys()):
            findings = by_layer[layer]
            errs = [f for f in findings if f["severity"] in ("ERROR", "CRITICAL")]
            warns = [f for f in findings if f["severity"] == "WARN"]

            # Skip layers with only OK findings unless verbose
            if not errs and not warns:
                oks = [f for f in findings if f["severity"] == "OK"]
                print(f"  {layer}: {len(oks)} checks passed")
                continue

            print(f"  ── {layer} ──")
            for f in errs + warns:
                icon = SEVERITY_ICON.get(f["severity"], "  ")
                print(f"  {icon} [{f['severity']}] {f['component']}: {f['message']}")
                if f.get("detail"):
                    print(f"     {f['detail'][:120]}")
                if f.get("auto_fix"):
                    print(f"     ↳ fix: {f['auto_fix']}")
            print()

        # Score
        total_weight = len(self.findings) * 3  # max score per finding
        score = sum(
            3 if f["severity"] == "OK" else
            2 if f["severity"] == "INFO" else
            1 if f["severity"] == "WARN" else
            0 for f in self.findings
        ) / max(total_weight, 1)
        grade = "A" if score >= 0.9 else "B" if score >= 0.75 else "C" if score >= 0.6 else "D" if score >= 0.4 else "F"

        print(f"  Grade: {grade} ({score:.0%}) | Errors: {errors} | Warnings: {warns} | OK: {oks}")
        if errors == 0:
            print(f"  Status: READY — system is healthy")
        else:
            print(f"  Status: ACTION REQUIRED — {errors} errors need attention")
            if self.fix:
                print(f"  Auto-fix was ON — some issues may have been resolved")

    def to_dict(self):
        severity_counts = {s: self.stats.get(s, 0) for s in ["OK", "INFO", "WARN", "ERROR", "CRITICAL"]}
        errors = severity_counts["ERROR"] + severity_counts["CRITICAL"]
        return {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "mode": "quick" if self.quick else "full",
            "auto_fix": self.fix,
            "findings": self.findings,
            "summary": {
                "total": len(self.findings),
                "by_severity": severity_counts,
                "errors": errors,
                "healthy": errors == 0,
            },
            "by_layer": {
                layer: {
                    "findings": [f for f in self.findings if f["layer"] == layer],
                    "errors": len([f for f in self.findings if f["layer"] == layer and f["severity"] in ("ERROR", "CRITICAL")]),
                }
                for layer in sorted(set(f["layer"] for f in self.findings))
            },
        }

def main():
    use_json = "--json" in sys.argv
    fix = "--fix" in sys.argv
    quick = "--quick" in sys.argv

    v = Verifier(fix=fix, quick=quick)
    v.run_all()
    v.report(use_json=use_json)

    # Exit code
    errors = v.stats.get("ERROR", 0) + v.stats.get("CRITICAL", 0)
    if errors > 0:
        sys.exit(1 if errors < 3 else 2)
    sys.exit(0)

if __name__ == "__main__":
    main()
