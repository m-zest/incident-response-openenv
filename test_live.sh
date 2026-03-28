#!/bin/bash
URL="https://m-zest-incident-response-env-sre.hf.space"
echo "=== Testing Live Space ==="

# 1. Health
echo -n "Health: "
curl -s $URL/health | python3 -c "import sys,json; print('OK' if json.load(sys.stdin)['status']=='healthy' else 'FAIL')"

# 2. Dashboard
echo -n "Dashboard: "
curl -s $URL/ | head -1 | grep -q "DOCTYPE" && echo "OK" || echo "FAIL"

# 3. Reset
echo -n "Reset: "
curl -s -X POST $URL/reset -H "Content-Type: application/json" \
  -d '{"task_id":"easy"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('observation') else 'FAIL')"

# 4. Step
echo -n "Step: "
curl -s -X POST $URL/step -H "Content-Type: application/json" \
  -d '{"action":{"command":"list_alerts","target":"","parameters":{}}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('observation') else 'FAIL')"

# 5. Dockerfile exists
echo -n "Dockerfile: "
[ -f Dockerfile ] && echo "OK" || echo "FAIL"

# 6. inference.py exists
echo -n "inference.py: "
[ -f inference.py ] && echo "OK" || echo "FAIL"

# 7. Tests
echo -n "Tests: "
pytest -q 2>&1 | tail -1

echo "=== Done ==="

# 8. openenv.yaml exists
echo -n "openenv.yaml: "
[ -f openenv.yaml ] && echo "OK" || echo "FAIL"

# 9. State endpoint
echo -n "State: "
curl -s https://m-zest-incident-response-env-sre.hf.space/state | python3 -c "import sys,json; print('OK' if json.load(sys.stdin) else 'FAIL')" 2>/dev/null || echo "FAIL"

# 10. Tasks endpoint  
echo -n "Tasks: "
curl -s https://m-zest-incident-response-env-sre.hf.space/tasks | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK ({len(d)} tasks)' if len(d)>=3 else 'FAIL')" 2>/dev/null || echo "FAIL"

# 11. Grader scores in range
echo -n "Grader: "
curl -s https://m-zest-incident-response-env-sre.hf.space/grader | python3 -c "import sys,json; print('OK' if json.load(sys.stdin) else 'FAIL')" 2>/dev/null || echo "FAIL"

# 12. No stale files
echo -n "No stale server/: "
[ ! -d "server" ] && echo "OK" || echo "FAIL - delete server/"

echo -n "No baseline.py: "
[ ! -f "baseline.py" ] && echo "OK" || echo "FAIL - delete baseline.py"

# 13. LICENSE consistent
echo -n "License: "
grep -q "MIT" LICENSE 2>/dev/null && echo "OK" || echo "FAIL"
