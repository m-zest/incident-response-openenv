# Incident Response SRE Environment

**An On-Call Site Reliability Engineering Simulator for OpenEnv**

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compatible-blue)](https://github.com/meta-pytorch/OpenEnv)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

An OpenEnv-compatible reinforcement learning environment that simulates production infrastructure incidents. An AI agent acts as an on-call SRE engineer, triaging alerts, diagnosing root causes, and executing remediations across a simulated microservices cluster.

Built for the [OpenEnv AI Hackathon](https://pytorch.org/event/openenv-ai-hackathon/) (Meta x Hugging Face x PyTorch).

---

## Why This Environment?

Every production system fails. When it does, a human engineer must rapidly triage alerts, investigate logs, trace dependency chains, and execute the correct fix -- often under pressure and with incomplete information.

This environment captures that challenge as a standardized RL benchmark:

- **Real-world utility**: Models the exact workflow of on-call SRE engineers at companies like Meta, Google, and Amazon
- **Deterministic grading**: Scores based on objective system health metrics, not subjective judgment
- **Dense reward signals**: Partial credit for each investigative step, enabling effective RL training
- **Cross-domain reasoning**: Hard tasks blend reliability engineering with cybersecurity, requiring agents to distinguish between performance bugs and active security breaches

No equivalent environment exists in the OpenEnv Hub today.

---

## Environment Description

### The Simulated Cluster

The environment simulates a microservices architecture with interconnected services:

| Service | Role |
|---------|------|
| `frontend` | User-facing web application |
| `api-gateway` | Request routing and load balancing |
| `user-service` | User authentication and profiles |
| `payment-service` | Payment processing |
| `cache-redis` | In-memory caching layer |
| `database-primary` | PostgreSQL primary database |
| `worker-queue` | Background job processing |
| `log-server` | Centralized logging |
| `config-server` | Service mesh configuration |
| `dns-resolver` | Internal DNS resolution |

Services have dependency relationships. A failure in `database-primary` cascades through `user-service` -> `api-gateway` -> `frontend`.

### Action Space

The agent interacts via CLI-style commands:

| Command | Description |
|---------|-------------|
| `check_logs {service}` | View recent log entries |
| `get_metrics {service}` | View CPU, memory, disk, latency, connections |
| `list_alerts` | View all firing alerts |
| `check_dependencies {service}` | See upstream/downstream dependencies |
| `restart_service {service}` | Restart a service process |
| `scale_up {service}` | Add service replicas |
| `rollback_deploy {service}` | Roll back to previous version |
| `kill_process {service}` | Kill a process by PID (use parameters: {"pid": "1234"}) |
| `check_process_list {service}` | View running processes (detects malware) |
| `check_network {service}` | View network connections (detects exfiltration) |
| `submit_root_cause {description}` | Declare diagnosis (ends episode) |

### Observation Space

Each step returns:

- **output**: Terminal-style text result of the command
- **alerts**: Currently firing alerts with severity levels
- **system_health**: Overall health percentage (0-100)
- **score**: Cumulative score (0.0-1.0)
- **step_count / max_steps**: Progress tracking

---

## Tasks (Easy -> Medium -> Hard)

### Task 1: Easy -- Single Alert Triage
One service has a clear, isolated issue. The agent diagnoses and fixes it in 2-3 steps.

**Scenarios**: Disk full, process crash, failed deployment, memory leak, expired TLS certificate

**Expected agent performance**: ~0.85-0.95

### Task 2: Medium -- Correlated Multi-Service Failure
Multiple alerts fire simultaneously. The agent must trace the dependency chain to find the actual root cause, which is often 2-3 layers deep.

**Scenarios**: Database connection pool exhaustion, Redis cache eviction storm, message queue backlog, DNS resolution failure

**Expected agent performance**: ~0.40-0.60

### Task 3: Hard -- Cascading Failure with Security Ambiguity
Complex incidents where the root cause is ambiguous. The agent must distinguish between infrastructure failures and active security breaches using diagnostic tools.

**Scenarios**: Crypto-mining attack disguised as memory leak, cascading TLS failure from corrupted config push, DDoS attack vs legitimate traffic spike

**Expected agent performance**: ~0.10-0.25

---

## Scoring and Grading Logic

The grading formula is fully deterministic -- no LLM-as-judge, no subjectivity:

```
S = max(0, (H_final - H_initial) / (100 - H_initial) * omega - phi - psi)
```

| Variable | Description |
|----------|-------------|
| `H_initial` | System health at episode start |
| `H_final` | System health at episode end |
| `omega` | 1.0 if root cause correctly identified, 0.6 if fixed without diagnosis, 0.3 otherwise |
| `phi` | Efficiency penalty: 0.02 per step beyond optimal (max 0.3) |
| `psi` | Destructive action penalty: 0.15 per occurrence |

### Partial Rewards Per Step

| Agent Action | Reward | Rationale |
|-------------|--------|-----------|
| Check logs of root cause service | +0.08 | Investigating correctly |
| Check logs of other service | +0.01 | Gathering info |
| Correct remediation action | +0.25 | Major progress |
| Restart a healthy service | -0.05 | Calibrated restraint penalty |
| Correct root cause submission | +0.30 | Diagnostic bonus |
| Wrong root cause submission | -0.10 | Incorrect diagnosis penalty |

### Why Shotgun Debugging Fails

An agent that blindly restarts every service will:
- Fix the root cause eventually (+health)
- But accumulate massive efficiency penalties (-phi)
- And penalties for restarting healthy services (-0.05 each)
- Final score: ~0.35 instead of ~0.90

The environment rewards **precision and calibrated restraint**.

---

## Setup and Usage

### Prerequisites

- Python 3.10+
- Docker (for containerized deployment)
- OpenEnv core: `pip install openenv-core`

### Local Development

```bash
# Clone the repository
git clone https://github.com/m-zest/incident-response-openenv.git
cd incident-response-openenv

# Install dependencies
pip install -e ".[dev]"

# Copy the environment template and fill in your API keys
cp .env.example .env

# Run the server locally
uvicorn incident_response_env.server.app:app --host 0.0.0.0 --port 8000
```

### Run Tests

```bash
pytest tests/ -v
```

### Docker

```bash
# Build
docker build -t incident-response-env:latest .

# Run
docker run -p 8000:8000 incident-response-env:latest
```

### Deploy to Hugging Face Spaces

```bash
pip install huggingface_hub
huggingface-cli login
openenv push --repo-id m-zest/incident-response-env
```

---

## Baseline Scores

Computed using Groq API with Llama 3.3 70B (Chain-of-Thought prompting):

| Task | Mean Score | Scenarios |
|------|-----------|-----------|
| Easy | 0.91 | 5 |
| Medium | 0.52 | 4 |
| Hard | 0.18 | 3 |

### Running the Baseline

```bash
# Using Groq (free)
export OPENAI_API_KEY=your-groq-key
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
python baseline.py

# Using NVIDIA Nemotron (free tier)
export OPENAI_API_KEY=your-nvidia-key
export OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1
export MODEL_NAME=nvidia/llama-3.3-nemotron-super-49b-v1
python baseline.py
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ws` | WebSocket | Standard OpenEnv interaction (reset/step/state) |
| `/health` | GET | Health check |
| `/tasks` | GET | List available tasks with action schema |
| `/grader` | GET | Get grading result after episode completion |
| `/baseline` | GET | Get baseline scores for all tasks |

---

## Technical Design

### Architecture

```
+-----------------------------+        +----------------------------------+
|  Agent (LLM / RL Policy)    |        |  Docker Container (HF Spaces)    |
|                             |  WS    |                                  |
|  obs = env.reset("medium")  |<------>|  environment.py                  |
|  obs = env.step(action)     |        |    +-- infrastructure.py         |
|                             |        |    +-- grader.py                 |
|  Groq / Nemotron / OpenAI   |        |    +-- scenarios/*.json          |
+-----------------------------+        +----------------------------------+
```

### Key Design Decisions

1. **Text-based state machine**: All infrastructure is simulated as Python dicts. No real servers. Fast, deterministic, zero external dependencies.

2. **JSON-driven scenarios**: Scenarios are loaded from JSON files, making it easy to add new failure modes without changing code.

3. **Server-side state**: The environment maintains full state via WebSocket. The agent never needs to resend history.

4. **Calibrated restraint scoring**: Penalizes agents for acting on insufficient evidence -- the same skill required of real SRE engineers.

5. **Cross-domain tasks**: Hard scenarios blend SRE and cybersecurity, testing whether agents can pivot between operational domains.

---

## Project Structure

```
incident-response-openenv/
├── incident_response_env/         # Python package
│   ├── __init__.py                # Package exports
│   ├── models.py                  # Pydantic Action, Observation, State
│   ├── client.py                  # OpenEnv client (SREEnv)
│   ├── scenarios/
│   │   ├── easy.json              # 5 single-alert scenarios
│   │   ├── medium.json            # 4 correlated-failure scenarios
│   │   └── hard.json              # 3 cascading/security scenarios
│   └── server/
│       ├── __init__.py
│       ├── app.py                 # FastAPI server + extra endpoints
│       ├── environment.py         # Core OpenEnv Environment class
│       ├── infrastructure.py      # Simulated cluster engine
│       └── grader.py              # Deterministic scoring logic
├── tests/
│   └── test_environment.py        # Grader determinism + integration tests
├── baseline.py                    # LLM baseline inference script
├── .env.example                   # Environment variable template
├── Dockerfile                     # Container definition
├── requirements.txt               # Docker dependencies
├── openenv.yaml                   # Environment manifest
├── pyproject.toml                 # Build configuration
├── README.md                      # This file
└── LICENSE                        # MIT
```

---

## Author

**Mohammad Zeeshan** -- AI Researcher

---

## License

MIT License. See [LICENSE](LICENSE) for details.
