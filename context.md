# PROJECT CONTEXT FOR CLAUDE CODE

## What This Project Is

This is a submission for the **OpenEnv AI Hackathon** (Meta × Hugging Face × PyTorch). We are building an **Incident Response SRE Simulator** — a reinforcement learning environment where an AI agent acts as an on-call Site Reliability Engineer, diagnosing and fixing production infrastructure failures.

**Deadline: April 7, 2026 11:59 PM IST** (feature freeze target: April 5)

**Participant: Mohammad Zeeshan, solo**

---

## What Is OpenEnv?

OpenEnv is Meta's open-source framework for building standardized RL environments. Every environment exposes 3 methods:

```python
class Environment(ABC):
    def reset(self) -> Observation    # Start new episode
    def step(self, action) -> Observation  # Agent takes action, env responds
    @property
    def state(self) -> State          # Internal tracking
```

The environment runs inside a Docker container, deployed on HuggingFace Spaces. Communication happens over WebSocket. All data types use Pydantic models.

**Key package:** `openenv-core` (install via `pip install openenv-core`)
**Repo:** https://github.com/meta-pytorch/OpenEnv

---

## How The Environment Works

### Concept
The agent receives production alerts (server down, high CPU, database timeout, etc.) and must:
1. Triage alerts
2. Investigate logs and metrics
3. Identify the root cause
4. Execute the correct fix
5. Submit a root cause diagnosis

### Everything Is Simulated
There are NO real servers. The entire infrastructure is fake — Python dicts and strings loaded from JSON files. When the agent calls `check_logs server-3`, we just look up pre-written log strings from a dict and return them.

### 3 Difficulty Tiers (Required)
- **Easy** (5 scenarios): Single alert → single fix. E.g., disk full, process crash, bad deploy.
- **Medium** (4 scenarios): Multiple correlated alerts. Agent must trace dependency chain. E.g., database pool exhaustion causing cascading timeouts.
- **Hard** (3 scenarios): Cascading failures + ambiguity between SRE issues and security breaches. E.g., crypto-mining attack disguised as memory leak.

### 10 Agent Commands
```
check_logs {service}        — View log entries
get_metrics {service}       — View CPU/memory/disk/latency stats
list_alerts                 — View all firing alerts
check_dependencies {service} — See dependency graph
restart_service {service}   — Restart a service
scale_up {service}          — Add replicas
rollback_deploy {service}   — Roll back to previous version
check_process_list {service} — View running processes (detects malware)
check_network {service}     — View network connections (detects attacks)
submit_root_cause {text}    — Declare diagnosis (ends episode)
```

### Scoring Formula (Deterministic)
```
S = max(0, (H_final - H_initial) / (100 - H_initial) × Ω - Φ - Ψ)

Ω = 1.0 if root cause correctly identified
    0.6 if fixed without diagnosis
    0.3 otherwise
Φ = 0.02 per step beyond optimal (max 0.3)
Ψ = 0.15 per destructive action
```

Plus partial rewards per step:
- +0.08 for checking logs of the root cause service
- +0.01 for checking logs of other services
- +0.25 for correct remediation action
- -0.05 for restarting a healthy service
- +0.30 for correct root cause submission
- -0.10 for wrong root cause submission

---

## Project File Structure

```
incident-response-env/
├── __init__.py                 # Package exports
├── models.py                   # Pydantic: SREAction, SREObservation, SREState, Alert
├── client.py                   # OpenEnv client (SREEnv extends EnvClient)
├── baseline.py                 # LLM baseline script (connects Groq/Nemotron to env)
├── openenv.yaml                # OpenEnv manifest
├── pyproject.toml              # Dependencies
├── README.md                   # Documentation
├── LICENSE                     # MIT
├── .gitignore
├── .dockerignore
├── scenarios/
│   ├── easy.json               # 5 easy scenarios
│   ├── medium.json             # 4 medium scenarios
│   └── hard.json               # 3 hard scenarios
├── server/
│   ├── __init__.py
│   ├── app.py                  # FastAPI server + /tasks, /grader, /baseline endpoints
│   ├── environment.py          # Core Environment class: reset(), step(), state()
│   ├── infrastructure.py       # SimulatedCluster: processes commands, manages state
│   ├── grader.py               # Scoring formula + step rewards
│   ├── requirements.txt
│   └── Dockerfile
└── tests/
    ├── __init__.py
    └── test_environment.py     # 20 tests: grader determinism + integration
```

### How the files connect:
1. `models.py` defines the data types (Action, Observation, State)
2. `scenarios/*.json` contain the pre-built incident scenarios with fake logs/metrics
3. `server/infrastructure.py` loads scenarios and simulates the cluster (processes commands)
4. `server/grader.py` computes scores (step rewards + final score)
5. `server/environment.py` orchestrates everything (implements reset/step/state using infrastructure + grader)
6. `server/app.py` wraps the environment in FastAPI (3 lines + extra endpoints)
7. `baseline.py` connects an LLM to the environment and plays through all tasks
8. `client.py` is the OpenEnv client for external connections

---

## What Needs To Happen (In Order)

### Phase 1: Get It Running Locally
1. Install dependencies: `pip install openenv-core fastapi uvicorn pydantic websockets pytest`
2. Run tests: `pytest tests/test_environment.py -v`
3. Fix any import errors or bugs
4. Start server: `uvicorn incident_response_env.server.app:app --port 8000`
5. Test endpoints: `curl http://localhost:8000/tasks` and `curl http://localhost:8000/health`

### Phase 2: Run Baseline
1. Get free Groq API key from console.groq.com
2. Run: `OPENAI_API_KEY=key OPENAI_BASE_URL=https://api.groq.com/openai/v1 python baseline.py`
3. Check scores — target: easy ~0.9, medium ~0.5, hard ~0.2
4. If scores are off, adjust scenarios or grading weights

### Phase 3: Docker
1. Build: `docker build -t incident-response-env:latest -f server/Dockerfile .`
2. Run: `docker run -p 8000:8000 incident-response-env:latest`
3. Test the containerized version

### Phase 4: Deploy to HuggingFace Spaces
1. `pip install huggingface_hub && huggingface-cli login`
2. `openenv push --repo-id m-zest/incident-response-env`
3. Verify the live URL responds

### Phase 5: Submit
1. Paste the HF Spaces URL on the Scaler hackathon dashboard
2. Done

---

## Hackathon Evaluation Criteria

The judges evaluate:
1. **Real-world utility (30%)**: Does it model a genuine task?
2. **Task & grader quality (25%)**: 3+ tasks, deterministic graders, difficulty curve
3. **Environment design (20%)**: Clean state management, good reward shaping
4. **Code quality & spec compliance (15%)**: OpenEnv spec, typed models, Dockerfile works
5. **Creativity & novelty (10%)**: Novel domain

### Automated Evaluation
- **Phase 1**: Bot checks if HF Space deploys, reset() works, /tasks returns 3 tasks, Dockerfile builds
- **Phase 2**: NVIDIA Nemotron 3 Super (or similar LLM) plays through all 3 tasks. They check the difficulty curve.
- **Phase 3**: Human review by Meta/HF engineers (top submissions only)

---

## Important Technical Notes

- The `step()` function must be FAST and non-blocking. The evaluator LLM processes at high speed.
- All scoring must be deterministic: same actions → same score, always.
- The environment must work via WebSocket (OpenEnv default) AND the extra REST endpoints (/tasks, /grader, /baseline).
- Scenarios are loaded from JSON files in the scenarios/ directory.
- The baseline.py uses the OpenAI Python client pointed at Groq (free) or NVIDIA (free tier). It reads OPENAI_API_KEY and OPENAI_BASE_URL from environment variables.
- The Dockerfile should produce a container that starts the FastAPI server on port 8000.

---

## Common Issues You Might Hit

1. **Import paths**: The package structure uses relative imports (`from ..models import`). Make sure PYTHONPATH includes the parent directory, or install with `pip install -e .`
2. **openenv-core not found**: Install with `pip install openenv-core`. If it fails, try `pip install git+https://github.com/meta-pytorch/OpenEnv.git`
3. **Scenario files not found**: The `infrastructure.py` looks for scenarios relative to its own file path. If running from a different directory, the path resolution might break. Check `SCENARIOS_DIR` in `infrastructure.py`.
4. **WebSocket issues**: OpenEnv uses WebSocket at `/ws`. Make sure `create_fastapi_app()` sets this up correctly.
5. **Docker PYTHONPATH**: The Dockerfile sets `PYTHONPATH=/app`. The package is copied to `/app/incident_response_env/`. The uvicorn command references `incident_response_env.server.app:app`.

---

## Key Dependencies

```
openenv-core>=0.2.1      # OpenEnv framework
fastapi>=0.104.0         # Web server
uvicorn>=0.24.0          # ASGI server
pydantic>=2.0.0          # Data models
websockets>=12.0         # WebSocket support
pytest>=7.0.0            # Testing (dev)
openai>=1.0.0            # Baseline script (dev)
```

---

## Quick Reference: OpenEnv API

```python
from openenv.core.env_server import Environment, create_fastapi_app

class MyEnvironment(Environment):
    def reset(self) -> MyObservation:
        # Initialize new episode
        pass
    
    def step(self, action: MyAction) -> MyObservation:
        # Process action, return observation
        pass
    
    @property
    def state(self) -> MyState:
        # Return internal state
        pass

# app.py — wrap in FastAPI
env = MyEnvironment()
app = create_fastapi_app(env, MyAction, MyObservation)
```

---

## GitHub Repo
https://github.com/m-zest/incident-response-env (private, will be made public before submission)

## Start by running the tests. Fix any errors. Then move to Phase 2.
