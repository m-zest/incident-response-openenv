---
title: SRE Incident Response Simulator
emoji: 🚨
colorFrom: red
colorTo: gray
sdk: docker
pinned: false
---

# Incident Response SRE Environment

An OpenEnv-compatible RL environment where an AI agent acts as an on-call SRE engineer diagnosing production infrastructure failures. 14 scenarios across 4 difficulty tiers test investigation, multi-step reasoning, security analysis, and calibrated restraint.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compatible-blue)](https://github.com/meta-pytorch/OpenEnv)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green)](https://python.org)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)

Built for the [OpenEnv AI Hackathon](https://pytorch.org/event/openenv-ai-hackathon/) (Meta x Hugging Face x PyTorch).

## Baseline: Human vs AI

| Tier | AI (Nemotron 3 Super 120B) | Human SRE | Gap | Scenarios |
|------|---------------------------|-----------|-----|-----------|
| Easy | 0.77 | 0.90 | 0.13 | 5 |
| Medium | 0.46 | 0.80 | 0.34 | 4 |
| Hard | 0.26 | 0.70 | 0.44 | 3 |
| Expert | 0.00 | 0.74 | 0.74 | 2 |

All 14 scenarios are fully solvable. A human SRE engineer completes expert-tier split-brain scenarios in 9 steps with score 0.74. Nemotron 3 Super (120B parameters) scores 0.00 on the same scenarios, demonstrating significant room for RL fine-tuning.

**Why the gap exists:**
- **Easy:** Single alert, obvious fix. AI handles it.
- **Medium:** Multi-service correlation required. AI struggles to trace dependency chains.
- **Hard:** Security ambiguity. AI cannot distinguish crypto-mining attacks from memory leaks, or DDoS from traffic spikes.
- **Expert:** Forensic investigation across partitioned systems. AI gets stuck in investigation loops without converging.

## Scoring Formula

```
S = max(0, (H_final - H_initial) / (100 - H_initial) * omega - phi - psi)
```

| Variable | Value |
|----------|-------|
| omega | 1.0 correct diagnosis, 0.8 fixed + timed out, 0.6 fixed + wrong diagnosis, 0.3 neither |
| phi | 0.02 per step beyond optimal (max 0.3) |
| psi | 0.15 per destructive action |

Step rewards: +0.08 investigating root cause service, +0.25 correct fix, +0.30 correct diagnosis, -0.05 restarting healthy service, -0.10 wrong diagnosis.

## Action Space (17 commands)

| Command | Description |
|---------|-------------|
| `check_logs {service}` | View recent log entries for a service |
| `get_metrics {service}` | View CPU, memory, disk, latency, connection stats |
| `list_alerts` | View all firing alerts (includes auto-resolving noise alerts) |
| `check_dependencies {service}` | See upstream/downstream service dependencies |
| `get_dependency_graph` | Full dependency tree with health status and impact ranking |
| `trace_failure {service}` | Trace upstream deps, downstream blast radius, unhealthy paths |
| `restart_service {service}` | Restart a service (heavy services take 2 steps) |
| `scale_up {service}` | Add service replicas |
| `rollback_deploy {service}` | Roll back to previous version |
| `kill_process {service}` | Kill a process by PID (requires prior `check_process_list`) |
| `check_process_list {service}` | View running processes (detects disguised malware) |
| `check_network {service}` | View network connections (detects C2 exfiltration) |
| `add_note {text}` | Save an observation to the evidence board |
| `view_notes` | Review saved observations with step numbers |
| `get_runbook` | Get the standard operating procedure for this incident type |
| `get_dependency_graph` | NetworkX-powered graph with PageRank impact analysis |
| `submit_root_cause {description}` | Declare diagnosis (ends episode) |

## Scenarios (14 total)

**Easy (5 scenarios, 10 steps max):**
Disk full on log server, worker queue process crash, failed API gateway deployment, memory leak in user service, expired TLS certificate on payment service.

**Medium (4 scenarios, 15 steps max):**
Database connection pool exhaustion, Redis cache eviction storm, message queue backlog causing worker starvation, internal DNS resolution failure.

**Hard (3 scenarios, 20 steps max):**
Crypto-mining attack disguised as memory leak (malware hidden as `[jvm-gc-thread-4]` among 10 processes), cascading TLS failure from corrupted config push (config-server looks healthy, no alerts point to it), DDoS attack vs legitimate traffic spike (must analyze multiple log entries to distinguish).

**Expert (2 scenarios, 25 steps max):**
Database split-brain during network partition (both nodes claim primary, writes diverging, must compare WAL positions), supply chain attack via compromised npm dependency (backdoor exfiltrating env vars across 3 services, security lockdown revokes tools mid-episode).

## Key Features

- **Dynamic state** -systems degrade each step (CPU +0.5/step, latency x1.08, health -1.5/step), cascading to dependents after step 4, warnings escalate to critical at step 5
- **Red herring alerts** -noise alerts (backups, GC, auto-scaling) appear alongside real alerts and auto-resolve after 2-3 steps
- **Action latency** -heavy services (database, Redis) take 2 steps to restart; agent can investigate while waiting
- **Runbooks** -per-scenario standard operating procedures via `get_runbook`
- **Evidence board** -`add_note` / `view_notes` for tracking hypotheses across steps
- **Dependency graph** -NetworkX-powered `trace_failure` with blast radius and unhealthy path detection
- **Kill process prerequisites** -security scenarios require `check_process_list` before `kill_process`
- **MCP tool discovery** -`GET /mcp/tools` returns JSON schemas; expert scenarios dynamically revoke tools mid-episode (security lockdown)
- **Post-mortem reports** -`GET /postmortem` returns structured incident timeline with efficiency rating
- **Seed reproducibility** -`reset(seed=42)` produces identical episodes
- **RL training ready** -`examples/train_with_trl.py` shows HuggingFace TRL GRPOTrainer integration

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/web` | GET | Interactive dashboard |
| `/health` | GET | Health check |
| `/tasks` | GET | List tasks with action/observation schemas |
| `/baseline` | GET | AI and human baseline scores |
| `/grader` | GET | Grading result after episode |
| `/postmortem` | GET | Structured incident report after episode |
| `/mcp/tools` | GET | MCP tool discovery (reflects lockdown state) |
| `/ws` | WebSocket | Standard OpenEnv agent connection |
| `/web/reset` | POST | Start new episode |
| `/web/step` | POST | Execute command |

## Running Locally

```bash
# From source
git clone https://github.com/m-zest/incident-response-openenv.git
cd incident-response-openenv
pip install -e ".[dev]"
uvicorn incident_response_env.server.app:app --host 0.0.0.0 --port 8000

# Docker
docker build -t incident-response-env:latest .
docker run -p 8000:8000 incident-response-env:latest

# Baseline (supports Groq, NVIDIA, OpenAI)
export OPENAI_API_KEY=your-key
export OPENAI_BASE_URL=https://api.groq.com/openai/v1
python baseline.py --task hard  # or: easy, medium, expert, or omit for all
```

## Architecture

`models.py` defines Pydantic types (Action, Observation, State). Scenario JSON files contain pre-built incidents with fake logs, metrics, processes, and network connections. `infrastructure.py` loads scenarios, manages the simulated cluster, processes commands, and handles time-evolving state via NetworkX dependency graphs. `grader.py` computes deterministic scores. `environment.py` orchestrates everything as an OpenEnv Environment (reset/step/state). `app.py` wraps it in FastAPI with WebSocket, REST endpoints, and the interactive web dashboard.

## Future Work

This environment is designed as a foundation for ongoing research. See [FUTURE_WORK.md](FUTURE_WORK.md) for the full technical roadmap.

Key directions:
- **Multi-agent orchestration** -triage, diagnosis, remediation, and communication as separate specialized agents
- **Hybrid-real infrastructure** -actual Redis, SQLite, Nginx inside the container with chaos-engineered failures
- **Continuous RL training pipeline** via TRL/GRPO with curriculum learning
- **Custom scenario builder** for company-specific topologies (JSON-driven, no code changes)
- **Cross-model benchmark leaderboard** with seed-based reproducible evaluation

## Tests

```bash
pytest tests/ -v
```

25 tests covering grader determinism, environment lifecycle, scenario loading, seeded reproducibility, and all 4 difficulty tiers.

## Project Structure

```
incident-response-openenv/
├── incident_response_env/
│   ├── models.py, client.py, __init__.py
│   ├── scenarios/ (easy.json, medium.json, hard.json, expert.json)
│   └── server/ (app.py, environment.py, infrastructure.py, grader.py)
├── tests/test_environment.py
├── examples/train_with_trl.py
├── baseline.py, Dockerfile, requirements.txt, pyproject.toml, openenv.yaml
```

## Author

**Mohammad Zeeshan**
