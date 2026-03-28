#!/bin/bash
set -e

echo "=== SRE Incident Response Environment ==="
echo "Starting hybrid-real infrastructure..."

# Start Redis in background (lightweight, in-memory only)
if command -v redis-server &> /dev/null; then
    redis-server \
        --daemonize yes \
        --maxmemory 50mb \
        --maxmemory-policy allkeys-lru \
        --save "" \
        --appendonly no \
        --loglevel warning
    echo "[OK] Redis started (50MB, no persistence)"
else
    echo "[SKIP] Redis not installed"
fi

# Create log directory
mkdir -p /tmp/sre_logs

# Initialize SQLite database
python -m incident_response_env.services.setup_db 2>&1 || echo "[SKIP] SQLite setup skipped"

# Start background log writer
python -m incident_response_env.services.fake_worker &
WORKER_PID=$!
echo "[OK] Background worker started (PID: $WORKER_PID)"

# Trap to clean up on shutdown
cleanup() {
    echo "Shutting down..."
    kill $WORKER_PID 2>/dev/null || true
    redis-cli shutdown nosave 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[OK] Infrastructure ready"
echo "Starting uvicorn on port 7860..."

# Start the application server
exec uvicorn incident_response_env.server.app:app --host 0.0.0.0 --port 7860
