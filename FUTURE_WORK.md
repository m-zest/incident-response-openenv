# Future Work

## 1. Multi-Agent Orchestration

The environment currently tests a single agent handling the full incident lifecycle. The next step is specialized agents collaborating on a single incident:

- **Triage agent** (small, fast model) -filters noise, deduplicates, prioritizes from hundreds of alerts
- **Diagnosis agent** (large reasoning model) -deep investigation, dependency chain tracing, hypothesis formation
- **Remediation agent** (tool-use model) -executes precise fixes, handles action latency and security lockdowns
- **Communication agent** (writing model) -writes post-mortem, notifies stakeholders, creates tickets

The environment is agent-agnostic. It accepts commands via WebSocket from any source. Whether one agent sends all 17 commands or four agents each send a subset, scoring works identically.

**Implementation:** Add `agent_id` field to SREAction, track per-agent history, add coordination penalties for duplicate work, extend post-mortem to show per-agent contribution.

## 2. Hybrid-Real Infrastructure

Run lightweight real services inside the Docker container alongside the simulation:

- **Redis** (50MB) -actual cache with real eviction metrics
- **SQLite** -actual database with 10K users, 50K transactions
- **Nginx** -actual web server returning real HTTP responses
- **Worker process** -actual background job processor
- **Chaos engine** -injects real failures (fill Redis memory, lock SQLite, kill worker PID, start CPU burner)

The hybrid approach: if real services are running, return real data. If unavailable, fall back to simulated JSON. Tests pass without real services. HF Spaces free tier can run Redis + SQLite.

## 3. Continuous RL Training Pipeline

The environment provides dense per-step rewards suitable for RL algorithms. See `examples/train_with_trl.py` for a reference TRL integration.

Full pipeline: connect GRPOTrainer, run 10K episodes with curriculum learning (easy first, then medium, then hard). Research questions: how many episodes to close the human-AI gap? Does chain-of-thought help during training? Can RL teach calibrated restraint?

## 4. Custom Scenario Builder

Teams define their own infrastructure failures in JSON without modifying Python code. Use cases: company-specific topologies, progressive difficulty training sets, community challenge packs, SRE education bootcamps.

## 5. Cross-Model Benchmark Leaderboard

Standardized seed-based evaluation across models. `reset(seed=42)` produces identical episodes. All models tested on the same scenarios with the same prompt template. Results published as a HuggingFace Dataset with community submissions via PR.

## Connection to Broader Research

**Adversarial AI assessment:** The multi-agent architecture extends to adversarial scenarios where attack agents create incidents while defensive agents detect them. Related work: [Parity Swarm](https://parity-swarn-v2-2.vercel.app/) ([paper](https://apartresearch.com/project/parity-swarm-using-populationbased-social-simulation-to-discover-ai-safety-monitor-blind-spots-c9qc)).

**AI governance:** The post-mortem system, evidence board, and deterministic scoring provide an auditable record of AI decision-making, extensible to EU AI Act requirements for high-risk AI transparency (Article 13) and human oversight (Article 14).

**Enterprise RL:** The same architecture (scenario JSON, command processing, hybrid scoring, MCP tool discovery) adapts to IT helpdesk, SOC analysis, cloud cost optimization, database administration, and compliance auditing.
