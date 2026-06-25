#!/usr/bin/env python3
"""webhook-server — lightweight HTTP server for GitHub webhooks and external triggers.
Usage:
  python3 webhook-server.py [--port 9000] [--secret <token>]

Endpoints:
  POST /webhook/github    — GitHub push/PR events → auto-verify + heal
  POST /webhook/trigger   — Generic trigger → run verify-all, auto-heal
  GET  /health            — Health check, returns system status
  GET  /status            — Full system status (verify-all output)

Start with: python3 webhook-server.py --port 9000
Then configure GitHub webhook to http://your-ip:9000/webhook/github
"""
import sys, json, os, io, hmac, hashlib, subprocess
from pathlib import Path
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HOME = Path(os.environ.get('USERPROFILE', os.path.expanduser('~')))
CLAUDE = HOME / '.claude'
SCRIPTS = CLAUDE / 'scripts'
WEBHOOK_LOG = CLAUDE / '.claude' / 'webhook_events.jsonl'

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False

def log_event(event_type, payload):
    entry = {"timestamp": datetime.now().isoformat(), "type": event_type, "payload": payload}
    WEBHOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WEBHOOK_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

def verify_signature(secret, body, signature):
    if not secret:
        return True
    if not signature:
        return False
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def run_command(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding='utf-8', errors='replace')
        return {"rc": result.returncode, "stdout": result.stdout[:2000]}
    except Exception as e:
        return {"rc": -1, "error": str(e)}

class WebhookHandler(BaseHTTPRequestHandler):
    secret = None

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if self.path == '/health':
            self._respond(200, {"status": "ok", "timestamp": datetime.now().isoformat()})
        elif self.path == '/status':
            result = run_command(["python3", str(SCRIPTS / "health-check.py")])
            self._respond(200, result)
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        # Verify signature if secret is set
        signature = self.headers.get('X-Hub-Signature-256', '')
        if self.secret and not verify_signature(self.secret, body, signature):
            self._respond(403, {"error": "invalid signature"})
            return

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"raw": body.decode('utf-8', errors='replace')[:1000]}

        if self.path == '/webhook/github':
            event_type = self.headers.get('X-GitHub-Event', 'unknown')
            log_event("github", {"event": event_type, "repo": payload.get("repository", {}).get("full_name", "unknown")})

            # Auto-run verify-all + auto-heal on push
            if event_type == 'push':
                verify_result = run_command(["python3", str(SCRIPTS / "verify-all.py"), "--json"])
                heal_result = run_command(["python3", str(SCRIPTS / "auto-heal.py"), "--dry-run"])
                self._respond(200, {"status": "processed", "event": event_type, "verify": verify_result, "heal": heal_result})
            elif event_type == 'pull_request':
                self._respond(200, {"status": "acknowledged", "event": event_type})
            else:
                self._respond(200, {"status": "ignored", "event": event_type})

        elif self.path == '/webhook/trigger':
            action = payload.get("action", "verify")
            log_event("trigger", payload)

            if action == "verify":
                result = run_command(["python3", str(SCRIPTS / "verify-all.py"), "--json"])
                self._respond(200, {"status": "ok", "action": "verify", "result": json.loads(result.get("stdout", "{}"))})
            elif action == "heal":
                result = run_command(["python3", str(SCRIPTS / "auto-heal.py"), "--dry-run"])
                self._respond(200, {"status": "ok", "action": "heal", "result": result})
            elif action == "health":
                result = run_command(["python3", str(SCRIPTS / "health-check.py")])
                self._respond(200, {"status": "ok", "action": "health", "result": result})
            else:
                self._respond(400, {"error": f"unknown action: {action}"})

        else:
            self._respond(404, {"error": "not found"})

def main():
    if not HTTP_AVAILABLE:
        print("webhook-server: requires Python http.server (built-in, should always be available)")
        return

    port = 9000
    secret = None
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        if arg == "--secret" and i + 1 < len(sys.argv):
            secret = sys.argv[i + 1]

    WebhookHandler.secret = secret

    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    print(f"WEBHOOK: listening on port {port}")
    print(f"  POST /webhook/github  — GitHub events → auto-verify + heal")
    print(f"  POST /webhook/trigger  — {'{'}\"action\": \"verify|heal|health\"{'}'}")
    print(f"  GET  /health          — health check")
    print(f"  GET  /status          — full system status")
    print(f"  Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWEBHOOK: stopped.")
        server.shutdown()

if __name__ == "__main__":
    main()
