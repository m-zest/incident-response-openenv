# Incident Response SRE Environment

An OpenEnv-compatible reinforcement learning environment that simulates production infrastructure incidents. An AI agent acts as an on-call SRE engineer — triaging alerts, diagnosing root causes, and executing remediations across a simulated microservices cluster.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compatible-blue)](https://github.com/meta-pytorch/OpenEnv)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

Built for the [OpenEnv AI Hackathon](https://pytorch.org/event/openenv-ai-hackathon/) (Meta x Hugging Face x PyTorch).

## Overview

Every production system fails. When it does, a human engineer must rapidly triage alerts, investigate logs, trace dependency chains, and execute the correct fix — often under pressure with incomplete information.

This environment captures that challenge as a standardized RL benchmark with:

- **14 scenarios** across 4 difficulty tiers (easy, medium, hard, expert)
- **17 agent commands** including investigation, remediation, forensics, and diagnosis
- **Deterministic scoring** — same actions always produce same scores, no LLM-as-judge
- **Dense reward signals** — partial credit per step enables effective RL training
- **Cross-domain reasoning** — hard/expert tasks blend SRE with cybersecurity
- **Dynamic state** — systems actively degrade over time, alerts escalate, noise alerts auto-resolve
- **Interactive web dashboard** with real-time health timeline, service dependency map, and post-mortem reports

## Quick Start

```bash
git clone https://github.com/m-zest/incident-response-openenv.git
cd incident-response-openenv
pip install -e ".[dev]"
cp .env.example .env
uvicorn incident_response_env.server.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/web` for the interactive dashboard.

## Action Space

| Command | Description |
|---------|-------------|
| `check_logs {service}` | View recent log entries |
| `get_metrics {service}` | View CPU, memory, disk, latency, connections |
| `list_alerts` | View all firing alerts (includes noise alerts that auto-resolve) |
| `check_dependencies {service}` | See upstream/downstream dependencies |
| `get_dependency_graph` | Full dependency tree with health status and impact analysis |
| `trace_failure {service}` | Trace upstream deps, downstream blast radius, unhealthy paths |
| `restart_service {service}` | Restart a service (heavy services take 2 steps) |
| `scale_up {service}` | Add service replicas |
| `rollback_deploy {service}` | Roll back to previous version |
| `kill_process {service}` | Kill a process by PID (requires prior `check_network` for security scenarios) |
| `check_process_list {service}` | View running processes (detects malware) |
| `check_network {service}` | View network connections (detects exfiltration) |
| `add_note {text}` | Save an observation to the evidence board |
| `view_notes` | Review saved observations with step numbers |
| `get_runbook` | Get the standard operating procedure for this incident type |
| `get_dependency_graph` | NetworkX-powered dependency analysis |
| `submit_root_cause {description}` | Declare diagnosis (ends episode) |

## Difficulty Tiers

| Tier | Scenarios | Expected Score | Description |
|------|-----------|---------------|-------------|
| **Easy** | 5 | ~0.85 | Single alert, isolated failure. Diagnose and fix in 2-3 steps. |
| **Medium** | 4 | ~0.50 | Correlated multi-service failures. Trace dependency chains 2-3 layers deep. |
| **Hard** | 3 | ~0.20 | Cascading failures with security ambiguity. Distinguish SRE issues from active breaches. |
| **Expert** | 2 | ~0.08 | Forensic investigation. Split-brain databases, supply chain attacks. |

## Scoring

Fully deterministic formula:

```
S = max(0, health_ratio * omega - phi - psi)

health_ratio = (H_final - H_initial) / (100 - H_initial)
omega        = 1.0 (correct diagnosis) | 0.8 (fixed, timed out) | 0.6 (fixed, no diagnosis) | 0.3 (neither)
phi          = 0.02 per step beyond optimal (max 0.3)
psi          = 0.15 per destructive action
```

**Step rewards:** +0.08 investigating root cause service, +0.25 correct fix, +0.30 correct diagnosis, -0.05 restarting healthy service, -0.10 wrong diagnosis.

## Key Features

**Dynamic State:** Systems degrade over time. CPU and latency worsen each step. After step 4, failures cascade to dependent services. After step 5, warnings escalate to critical.

**Noise Alerts:** Red herring alerts (scheduled backups, GC runs, auto-scaling checks) appear alongside real alerts and auto-resolve after 2-3 steps. Agents must distinguish signal from noise.

**Action Latency:** Heavy services (database, Redis) take 2 steps to restart. Agents can investigate other services while waiting.

**Runbooks:** Each scenario provides a standard operating procedure via `get_runbook`. Guides optimal investigation order.

**Evidence Board:** `add_note` / `view_notes` lets agents track observations and hypotheses across investigation steps.

**Dependency Graph:** NetworkX-powered graph analysis. `trace_failure` reveals upstream/downstream blast radius and identifies unhealthy paths.

**Kill Process:** Security scenarios require `check_network` before `kill_process` works — agents must confirm the threat before acting.

**Post-Mortem:** After each episode, `GET /postmortem` returns a structured incident report with timeline, efficiency rating, and evidence notes.

**MCP Tool Discovery:** `GET /mcp/tools` returns available commands as JSON schemas. During expert security scenarios, tools are dynamically revoked mid-episode (security lockdown) — the agent must adapt when `restart_service` and `scale_up` become unavailable.

**RL Training Ready:** Includes `examples/train_with_trl.py` showing how to connect to HuggingFace TRL's GRPOTrainer. The deterministic grader provides the reward signal.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Redirect to web dashboard |
| `/web` | GET | Interactive SRE dashboard |
| `/ws` | WebSocket | Standard OpenEnv interaction |
| `/health` | GET | Health check |
| `/tasks` | GET | Available tasks with action/observation schemas |
| `/grader` | GET | Grading result after episode completion |
| `/baseline` | GET | Pre-computed baseline scores |
| `/postmortem` | GET | Structured post-mortem incident report |
| `/mcp/tools` | GET | MCP-compatible tool discovery (dynamic, reflects lockdown state) |

## Docker

```bash
docker build -t incident-response-env:latest .
docker run -p 8000:8000 incident-response-env:latest
```

## Baseline

```bash
export OPENAI_API_KEY=your-groq-key
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
python baseline.py
```

Supports Groq, NVIDIA Nemotron, and OpenAI. Includes automatic retry with exponential backoff on rate limits.

## Tests

```bash
pytest tests/ -v
```

25 tests covering grader determinism, environment lifecycle, scenario loading, and seeded reproducibility.

## Project Structure

```
incident-response-openenv/
├── incident_response_env/
│   ├── __init__.py
│   ├── models.py                  # Pydantic Action, Observation, State
│   ├── client.py                  # OpenEnv client
│   ├── scenarios/
│   │   ├── easy.json              # 5 scenarios
│   │   ├── medium.json            # 4 scenarios
│   │   ├── hard.json              # 3 scenarios
│   │   └── expert.json            # 2 scenarios
│   └── server/
│       ├── app.py                 # FastAPI + web dashboard
│       ├── environment.py         # OpenEnv Environment class
│       ├── infrastructure.py      # Simulated cluster engine
│       └── grader.py              # Deterministic scoring
├── tests/
│   └── test_environment.py
├── baseline.py
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── openenv.yaml
├── .env.example
└── LICENSE
```

## Author

**Mohammad Zeeshan**

## License

MIT
