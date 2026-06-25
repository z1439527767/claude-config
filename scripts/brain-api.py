#!/usr/bin/env python3
"""brain-api — REST API for Ralph's persistent brain.
Exposes brain state, engine triggers, and context injection endpoints.

Endpoints:
  GET  /health              — Is the brain alive?
  GET  /status              — Full brain status (all engines)
  GET  /mode                — Current mode (conscious/subconscious)
  POST /mode/{mode}         — Switch mode
  POST /trigger/{engine}    — Manually trigger an engine
  GET  /inject              — Context injection for Claude Code
  GET  /dashboard           — HTML dashboard
  GET  /engines             — List all engines
  GET  /engine/{name}/status — Specific engine status
  GET  /alerts              — Current alerts
  GET  /history             — Recent cycle history
"""
import sys, os, json, time, subprocess
from pathlib import Path
from datetime import datetime

# Try FastAPI, fallback to simple HTTP server
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    USE_FASTAPI = True
except ImportError:
    USE_FASTAPI = False

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
SCRIPTS = HOME / 'scripts'
STATE_FILE = CLAUDE / '.claude' / 'brain_state.json'
LOCK_FILE = CLAUDE / '.claude' / 'brain.lock'

ENGINES = {
    "interoception":  {"script": "interoception.py",  "desc": "Internal state sensing (insula)"},
    "subconscious":   {"script": "subconscious.py",   "desc": "Background pattern detection"},
    "curiosity":      {"script": "curiosity-engine.py","desc": "Knowledge gap discovery"},
    "intuition":      {"script": "intuition-engine.py","desc": "Fast pattern matching (System 1)"},
    "immune":         {"script": "immune-system.py",   "desc": "Proactive defense system"},
    "narrative":      {"script": "narrative-engine.py","desc": "Storytelling memory"},
    "identity":       {"script": "identity-journal.py","desc": "Self-model & growth tracking"},
    "memory":         {"script": "memory-search.py",   "desc": "Memory search & scoring"},
    "consolidator":   {"script": "memory-consolidator.py","desc": "Memory distillation"},
    "salience":       {"script": "salience-gate.py",   "desc": "Attention filter (thalamus)"},
    "neuromodulation":{"script": "neuromodulation.py", "desc": "Reward/punishment learning"},
}

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"cycles": 0, "mode": "unknown", "started": None}

def is_alive():
    if not LOCK_FILE.exists():
        return False
    try:
        ts = datetime.fromisoformat(LOCK_FILE.read_text().strip())
        return (datetime.now() - ts).total_seconds() < 120
    except Exception:
        return False

def run_engine(name, *args, timeout=15):
    """Run an engine script. Returns (ok, output)."""
    if name not in ENGINES:
        return False, f"Unknown engine: {name}"

    script = SCRIPTS / ENGINES[name]["script"]
    if not script.exists():
        return False, f"Script not found: {script}"

    try:
        cmd = [sys.executable, str(script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout + result.stderr)[:2000]
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)

def get_injection():
    """Run all inject engines for Claude Code context."""
    injectors = [
        ("identity-journal.py", "--inject"),
        ("intuition-engine.py", "--inject"),
        ("immune-system.py", "--inject"),
        ("interoception.py", "--inject"),
        ("salience-gate.py", "--inject"),
    ]
    lines = []
    for script, arg in injectors:
        ok, output = run_engine(Path(script).stem, arg, timeout=5) if False else (True, "")
        # Run directly
        s = SCRIPTS / script
        if s.exists():
            try:
                r = subprocess.run([sys.executable, str(s), arg], capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    lines.append(r.stdout.strip())
            except Exception:
                pass
    return '\n\n'.join(lines)

def get_status():
    """Get full brain status."""
    state = load_state()
    alive = is_alive()

    engine_status = {}
    for name in ENGINES:
        ok, _ = run_engine(name, "--inject" if name != "consolidator" else "--json", timeout=5)
        engine_status[name] = "ok" if ok else "unknown"

    return {
        "alive": alive,
        "uptime_cycles": state.get("cycles", 0),
        "mode": state.get("mode", "unknown"),
        "started": state.get("started"),
        "conscious_cycles": state.get("conscious_cycles", 0),
        "subconscious_cycles": state.get("subconscious_cycles", 0),
        "dreams": state.get("dreams", 0),
        "alerts_raised": state.get("alerts_raised", 0),
        "engines": engine_status,
        "timestamp": datetime.now().isoformat(),
    }

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ralph Loop — Brain Dashboard</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background:#0a0a0f; color:#e0e0e0; padding:2rem; }
  h1 { color:#00d4ff; font-size:2rem; margin-bottom:.5rem; }
  .subtitle { color:#666; margin-bottom:2rem; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:1rem; }
  .card { background:#1a1a2e; border:1px solid #2a2a4e; border-radius:8px; padding:1.2rem; }
  .card h3 { color:#00d4ff; font-size:.9rem; text-transform:uppercase; margin-bottom:.8rem; }
  .status-bar { display:flex; align-items:center; gap:.5rem; margin:.5rem 0; }
  .bar { flex:1; height:6px; background:#2a2a4e; border-radius:3px; }
  .bar-fill { height:100%; border-radius:3px; transition:width .5s; }
  .alive { background:#00ff88; } .dead { background:#ff4444; }
  .metric { font-size:1.5rem; font-weight:bold; color:#fff; }
  .label { color:#888; font-size:.8rem; }
  .mode-conscious { color:#00ff88; } .mode-subconscious { color:#4488ff; }
</style>
</head>
<body>
<h1>🧠 Ralph Loop — Brain Dashboard</h1>
<p class="subtitle">Persistent autonomous agent · 24/7 evolution</p>
<div class="grid" id="grid">Loading...</div>
<script>
async function refresh() {
  try {
    const r = await fetch('/status');
    const d = await r.json();
    document.getElementById('grid').innerHTML = `
      <div class="card">
        <h3>🧠 Status</h3>
        <div class="status-bar"><div class="bar"><div class="bar-fill ${d.alive?'alive':'dead'}" style="width:${d.alive?'100':'30'}%"></div></div></div>
        <div class="metric ${d.alive?'alive':'dead'}">${d.alive?'ALIVE':'DOWN'}</div>
        <div class="label">Mode: <span class="${d.mode=='conscious'?'mode-conscious':'mode-subconscious'}">${d.mode}</span></div>
      </div>
      <div class="card">
        <h3>📊 Cycles</h3>
        <div class="metric">${d.uptime_cycles}</div>
        <div class="label">Conscious: ${d.conscious_cycles} | Subconscious: ${d.subconscious_cycles}</div>
      </div>
      <div class="card">
        <h3>💭 Dreams</h3>
        <div class="metric">${d.dreams}</div>
        <div class="label">Creative recombinations</div>
      </div>
      <div class="card">
        <h3>⚠️ Alerts</h3>
        <div class="metric">${d.alerts_raised}</div>
        <div class="label">Issues detected & raised</div>
      </div>
      ${Object.entries(d.engines).map(([name,status]) => `
        <div class="card">
          <h3>${name}</h3>
          <div class="status-bar"><div class="bar"><div class="bar-fill ${status=='ok'?'alive':'dead'}" style="width:${status=='ok'?'100':'30'}%"></div></div></div>
          <div class="label">${status}</div>
        </div>
      `).join('')}
    `;
  } catch(e) { document.getElementById('grid').innerHTML = '<p>Brain offline</p>'; }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

# ═══════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════

if USE_FASTAPI:
    app = FastAPI(title="Ralph Loop Brain API", version="4.0")

    @app.get("/health")
    async def health():
        alive = is_alive()
        return {"status": "ok" if alive else "down", "alive": alive}

    @app.get("/status")
    async def status():
        return get_status()

    @app.get("/mode")
    async def get_mode():
        state = load_state()
        return {"mode": state.get("mode", "unknown")}

    @app.post("/mode/{mode}")
    async def set_mode(mode: str):
        if mode not in ("conscious", "subconscious"):
            raise HTTPException(400, "Mode must be conscious or subconscious")
        os.environ["RALPH_MODE"] = mode
        return {"mode": mode}

    @app.post("/trigger/{engine}")
    async def trigger(engine: str):
        if engine == "all":
            results = {}
            for name in ENGINES:
                ok, output = run_engine(name, timeout=10)
                results[name] = {"ok": ok, "output": output[:200]}
            return {"triggered": "all", "results": results}

        ok, output = run_engine(engine, timeout=15)
        if not ok and "Unknown engine" in output:
            raise HTTPException(404, output)
        return {"engine": engine, "ok": ok, "output": output[:500]}

    @app.get("/inject")
    async def inject():
        return {"context": get_injection()}

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.get("/engines")
    async def list_engines():
        state = load_state()
        return {
            "engines": [
                {"name": name, "description": info["desc"],
                 "status": state.get("engine_status", {}).get(name, "unknown")}
                for name, info in ENGINES.items()
            ]
        }

    @app.get("/engine/{name}/status")
    async def engine_status(name: str):
        if name not in ENGINES:
            raise HTTPException(404, f"Unknown engine: {name}")
        state = load_state()
        return {
            "name": name,
            "description": ENGINES[name]["desc"],
            "status": state.get("engine_status", {}).get(name, "unknown"),
        }

    @app.get("/alerts")
    async def alerts():
        state = load_state()
        return {"alerts_raised": state.get("alerts_raised", 0)}

    @app.get("/history")
    async def history():
        state = load_state()
        return {"cycles": state.get("cycle_log", [])[-10:]}

    def start():
        port = int(os.environ.get("RALPH_CONSCIOUS_PORT", "9020"))
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

else:
    # Fallback: simple HTTP server
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class BrainHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                alive = is_alive()
                self._json({"status": "ok" if alive else "down", "alive": alive})
            elif self.path == "/status":
                self._json(get_status())
            elif self.path == "/dashboard":
                self._html(DASHBOARD_HTML)
            elif self.path == "/inject":
                self._json({"context": get_injection()})
            else:
                self._json({"error": "not found"}, 404)

        def _json(self, data, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        def _html(self, html, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, format, *args):
            pass  # Quiet

    def start():
        port = int(os.environ.get("RALPH_CONSCIOUS_PORT", "9020"))
        server = HTTPServer(("0.0.0.0", port), BrainHandler)
        print(f"Brain API: http://0.0.0.0:{port}")
        server.serve_forever()

if __name__ == "__main__":
    start()
