#!/usr/bin/env bash
set -uo pipefail

PING_URL="${1:-}"
REPO_DIR="${2:-.}"

if [ -z "$PING_URL" ]; then
  echo "Usage: $0 <ping_url> [repo_dir]"
  exit 1
fi

PING_URL="${PING_URL%/}"
PASS=0
FAIL=0

check() {
  local name="$1" result="$2"
  if [ "$result" -eq 0 ]; then
    echo "✓ $name"
    PASS=$((PASS+1))
  else
    echo "✗ $name"
    FAIL=$((FAIL+1))
  fi
}

# 1. HF Space responds
echo "=== Checking HF Space ==="
curl -sf "$PING_URL/health" > /dev/null 2>&1
check "HF Space health" $?

# 2. Reset endpoint
echo "=== Checking Reset ==="
curl -sf -X POST "$PING_URL/reset" -H "Content-Type: application/json" -d '{"task_id":"easy"}' > /dev/null 2>&1
check "POST /reset" $?

# 3. Dockerfile exists
echo "=== Checking Files ==="
[ -f "$REPO_DIR/Dockerfile" ]
check "Dockerfile exists" $?

# 4. inference.py exists
[ -f "$REPO_DIR/inference.py" ]
check "inference.py exists" $?

# 5. openenv.yaml exists
[ -f "$REPO_DIR/openenv.yaml" ]
check "openenv.yaml exists" $?

# 6. openenv validate
echo "=== Running openenv validate ==="
if command -v openenv &>/dev/null; then
  cd "$REPO_DIR" && openenv validate 2>/dev/null
  check "openenv validate" $?
else
  echo "⚠ openenv not installed, skipping validate"
fi

# 7. Docker build
echo "=== Docker Build ==="
if command -v docker &>/dev/null; then
  cd "$REPO_DIR" && docker build -t validate-test . > /dev/null 2>&1
  check "Docker build" $?
else
  echo "⚠ Docker not available, skipping build"
fi

echo ""
echo "=== Results ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ "$FAIL" -eq 0 ]; then
  echo "✓ All checks passed!"
else
  echo "✗ Some checks failed"
  exit 1
fi
