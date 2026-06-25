#!/bin/bash
# Ralph Brain Entrypoint — Starts daemon + API
set -e

echo "╔══════════════════════════════════════════╗"
echo "║  🧠 RALPH LOOP — Brain Container v4.0    ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Mode:      ${RALPH_MODE:-auto}"
echo "  Cycle:     ${RALPH_CYCLE_SECONDS:-60}s"
echo "  API port:  ${RALPH_CONSCIOUS_PORT:-9020}"
echo ""

# Create required directories
mkdir -p /home/ralph/.claude/hook_perf
mkdir -p /home/ralph/.claude/session_history
mkdir -p /home/ralph/blackboard/subconscious
mkdir -p /home/ralph/blackboard/curiosity
mkdir -p /home/ralph/blackboard/salience
mkdir -p /home/ralph/packed

# Start Brain API in background
echo "  [1/2] Starting Brain API..."
python3 /home/ralph/scripts/brain-api.py &
API_PID=$!
sleep 2

# Verify API is up
if curl -s http://localhost:${RALPH_CONSCIOUS_PORT:-9020}/health > /dev/null 2>&1; then
    echo "  [1/2] Brain API: ✅ ready"
else
    echo "  [1/2] Brain API: ⚠️  starting (may need a moment)"
fi

# Start Brain Daemon (foreground)
echo "  [2/2] Starting Brain Daemon..."
python3 /home/ralph/scripts/brain-daemon.py

# Cleanup on exit
kill $API_PID 2>/dev/null || true
echo "  Brain container shutting down."
