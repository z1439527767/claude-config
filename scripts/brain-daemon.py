#!/usr/bin/env python3
"""brain-daemon — Ralph's 24/7 continuous brain loop.
Keeps the brain alive forever. Cycles through: Sense → Think → Act → Rest.

Two modes:
  CONSCIOUS:    Claude Code session active → full processing, fast cycle
  SUBCONSCIOUS: No active session → background processing, slow cycle

The daemon never stops. Even when "resting", it dreams and consolidates.
"""
import sys, os, json, time, signal, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
SCRIPTS = HOME / 'scripts'
BRAIN_LOG = CLAUDE / 'brain_daemon.log'
STATE_FILE = CLAUDE / '.claude' / 'brain_state.json'
LOCK_FILE = CLAUDE / '.claude' / 'brain.lock'
SESSION_FLAG = CLAUDE / 'session-env' / 'active_session'

# ── Daemon State ──

def log(msg):
    """Write to daemon log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(BRAIN_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {
        "started": datetime.now().isoformat(),
        "cycles": 0,
        "mode": "conscious",
        "conscious_cycles": 0,
        "subconscious_cycles": 0,
        "dreams": 0,
        "alerts_raised": 0,
        "last_evolved": None,
        "engine_status": {},
    }

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

def detect_mode():
    """Detect if a Claude Code session is active."""
    # Check for active session flag (written by SessionStart hook)
    if SESSION_FLAG.exists():
        try:
            ts = datetime.fromisoformat(SESSION_FLAG.read_text().strip())
            if (datetime.now() - ts).total_seconds() < 300:  # Active within 5 min
                return "conscious"
        except Exception:
            pass
    return "subconscious"

def run_engine(script_name, *args, timeout=30):
    """Run a brain engine script safely. Returns (success, output)."""
    script = SCRIPTS / script_name
    if not script.exists():
        return False, f"Script not found: {script_name}"

    try:
        cmd = [sys.executable, str(script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = result.returncode == 0
        output = (result.stdout + result.stderr)[:2000]
        return ok, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════

def main_loop():
    """The infinite brain loop. Sense → Think → Act → Rest."""
    state = load_state()
    state["started"] = datetime.now().isoformat()
    save_state(state)

    log("🧠 BRAIN DAEMON STARTED — Ralph is alive")
    log(f"   Mode: {detect_mode()} | Cycle: every 60s")

    # Write lock file (for health checks)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    cycle_log = deque(maxlen=100)

    while True:
        try:
            cycle_start = time.time()
            state = load_state()
            mode = detect_mode()
            state["mode"] = mode
            state["cycles"] += 1

            # ═══ SENSE: Internal State ═══
            log(f"[CYCLE {state['cycles']}] SENSE ({mode})")
            ok, output = run_engine("interoception.py", "--feel", timeout=10)
            state["engine_status"]["interoception"] = "ok" if ok else "fail"

            # ═══ THINK: Background Processing ═══
            log(f"[CYCLE {state['cycles']}] THINK")

            if mode == "subconscious":
                # Idle mode: run subconscious dream every N cycles
                if state["cycles"] % 60 == 0:  # ~hourly
                    ok, _ = run_engine("subconscious.py", "--mode", "dream", timeout=30)
                    state["dreams"] += 1
                    state["engine_status"]["subconscious"] = "ok" if ok else "fail"

                # Memory scoring every 10 cycles (~10 min)
                if state["cycles"] % 10 == 0:
                    run_engine("memory-search.py", "--stats", timeout=10)

                # Curiosity scan every 30 cycles (~30 min)
                if state["cycles"] % 30 == 0:
                    ok, output = run_engine("curiosity-engine.py", timeout=20)
                    if ok and "0 gaps" not in output:
                        state["alerts_raised"] += 1
                    state["engine_status"]["curiosity"] = "ok" if ok else "fail"

            # ═══ ACT: Auto-Healing ═══
            log(f"[CYCLE {state['cycles']}] ACT")

            # Run immune system scan every 50 cycles
            if state["cycles"] % 50 == 0:
                ok, output = run_engine("immune-system.py", "--scan", timeout=15)
                state["engine_status"]["immune"] = "ok" if ok else "fail"
                if "issues found" in output:
                    state["alerts_raised"] += 1

            # Rebuild intuition index every 100 cycles
            if state["cycles"] % 100 == 0:
                ok, _ = run_engine("intuition-engine.py", "--rebuild", timeout=15)
                state["engine_status"]["intuition"] = "ok" if ok else "fail"
                state["last_evolved"] = datetime.now().isoformat()

            # Salience gate adaptation every 20 cycles
            if state["cycles"] % 20 == 0:
                run_engine("salience-gate.py", "--inject", timeout=5)

            # ═══ REST: Consolidation ═══
            log(f"[CYCLE {state['cycles']}] REST")

            # Memory consolidator trigger check every 200 cycles (~3.3h)
            if state["cycles"] % 200 == 0:
                ok, output = run_engine("memory-consolidator.py", "--force", timeout=30)
                state["engine_status"]["consolidator"] = "ok" if ok else "fail"

            # Identity reflection every 150 cycles
            if state["cycles"] % 150 == 0:
                run_engine("identity-journal.py", "--reflect", timeout=10)

            # ═══ SAVE STATE ═══
            elapsed = time.time() - cycle_start
            if mode == "conscious":
                state["conscious_cycles"] += 1
            else:
                state["subconscious_cycles"] += 1

            cycle_log.append({
                "cycle": state["cycles"],
                "mode": mode,
                "elapsed": round(elapsed, 1),
                "ts": datetime.now().isoformat(),
            })

            state["cycle_log"] = list(cycle_log)[-20:]
            save_state(state)

            # ═══ SLEEP ═══
            cycle_sec = int(os.environ.get('RALPH_CYCLE_SECONDS', '60'))
            if mode == "conscious":
                sleep_time = max(15, cycle_sec)  # Faster when session active
            else:
                sleep_time = max(30, cycle_sec)  # Slower when idle

            LOCK_FILE.write_text(datetime.now().isoformat())
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            log("🧠 BRAIN DAEMON SHUTDOWN — Goodnight")
            break
        except Exception as e:
            log(f"❌ CYCLE ERROR: {e}")
            time.sleep(10)  # Brief pause after error
            continue


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    main_loop()
