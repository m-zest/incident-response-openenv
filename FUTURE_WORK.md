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

## 6. eBPF-Based Real Observability

Instead of returning pre-written log strings from JSON, use eBPF (extended Berkeley Packet Filter) to capture real kernel-level telemetry from the hybrid services running inside the container. eBPF programs attach to kernel tracepoints and return actual system data without modifying the services themselves.

**What eBPF gives us:**

- **Real syscall tracing** - attach to `sys_enter_read`, `sys_enter_write`, `sys_enter_connect` to see exactly what Redis, SQLite, and Nginx are doing at the kernel level. When the agent runs `check_logs cache-redis`, instead of returning a pre-written string, we return actual I/O syscalls happening in real time.
- **Network packet inspection** - attach to `tcp_connect`, `tcp_retransmit_skb`, `tcp_drop` to capture real TCP state. The agent's `check_network` command returns actual connection tables, retransmit counts, and dropped packets from the kernel's perspective.
- **Process-level CPU profiling** - attach to `sched_switch` and `sched_process_exec` to track real CPU time per process. The crypto-mining scenario becomes fully real: the malicious process actually burns CPU, and `check_process_list` returns actual `/proc` data showing real resource consumption.
- **Filesystem monitoring** - attach to `vfs_write`, `vfs_read` to track disk I/O. The "disk full" scenario can use real disk fills, and metrics come from actual `statfs` calls.

**How it integrates with our environment:**

```python
# infrastructure.py - hybrid mode with eBPF
class HybridCluster(SimulatedCluster):
    def __init__(self, scenario, seed=None):
        super().__init__(scenario, seed)
        self._ebpf = EBPFCollector()  # attaches probes on init

    def _check_logs(self, service, parameters):
        if self._ebpf.is_available(service):
            # Return real kernel-level logs from eBPF ring buffer
            events = self._ebpf.read_events(service, limit=50)
            return format_ebpf_events(events)
        # Fall back to simulated logs
        return super()._check_logs(service, parameters)

    def _get_metrics(self, service):
        if self._ebpf.is_available(service):
            # Return real metrics from eBPF maps
            return self._ebpf.get_metrics(service)
        return super()._get_metrics(service)
```

**Implementation plan:**

1. Install `bcc-tools` or `bpftrace` in the Docker container (requires `--privileged` or `CAP_SYS_ADMIN`)
2. Create `ebpf_collector.py` with BPF programs for syscall tracing, network monitoring, and process profiling
3. Attach probes to the real Redis/SQLite/Nginx processes on startup
4. Route `check_logs`, `get_metrics`, `check_network`, `check_process_list` through eBPF when available
5. Fall back to simulated data when eBPF is unavailable (unprivileged containers, CI, tests)

**Limitation:** eBPF requires `CAP_SYS_ADMIN` or a privileged container. HF Spaces free tier likely cannot run it. This is a research direction for self-hosted or GPU-tier deployments.

## 7. Shadow Mode (Passive Learning from Production)

Shadow mode lets the environment learn from real production incidents without ever touching production systems. The agent observes a real incident in read-only mode, makes decisions in parallel, and gets scored on whether its actions would have been correct.

**How it works:**

```
PRODUCTION (real)                    SHADOW ENV (our simulator)

Alert fires: DB pool exhausted  -->  Agent receives same alert

Human SRE checks logs          -->  Agent decides: check_logs db
Human SRE restarts DB          -->  Agent decides: check_metrics db
                                     (different choice - tracked)
Human resolves in 4 steps      -->  Agent resolves in 7 steps

Post-mortem: human scored 0.85  -->  Shadow score: 0.52
                                     Gap: 0.33 (agent was slower,
                                     missed the dependency chain)
```

**The key insight:** the agent never touches production. It receives the same alerts and telemetry the human SRE received (via log replay or webhook forwarding), makes its own decisions independently, and gets scored against what actually happened.

**How it integrates with our environment:**

```python
# shadow_mode.py
class ShadowReplay:
    def __init__(self, incident_log: dict):
        """Replay a real incident through our simulated environment."""
        self.real_timeline = incident_log["timeline"]
        self.real_alerts = incident_log["alerts"]
        self.real_resolution = incident_log["resolution"]

    def create_scenario(self) -> dict:
        """Convert a real incident log into our scenario JSON format."""
        return {
            "id": f"shadow_{incident_log['id']}",
            "name": incident_log["title"],
            "initial_health": incident_log["health_at_alert"],
            "alerts": self.real_alerts,
            "services": self._build_services_from_logs(),
            "root_cause": incident_log["root_cause"],
            "root_cause_service": incident_log["root_cause_service"],
            "fix_action": incident_log["fix_action"],
            "optimal_steps": len(self.real_timeline),
        }

    def score_against_human(self, agent_actions: list) -> dict:
        """Compare agent's decisions to what the human SRE actually did."""
        return {
            "human_steps": len(self.real_timeline),
            "agent_steps": len(agent_actions),
            "action_overlap": self._compute_overlap(agent_actions),
            "time_to_diagnosis": self._time_to_first_correct_investigation(agent_actions),
            "would_have_resolved": self._check_resolution(agent_actions),
        }
```

**Data sources for shadow mode:**

- **PagerDuty/OpsGenie webhooks** - forward real alerts to the shadow environment
- **Datadog/Grafana log export** - replay real service logs as scenario input
- **Post-mortem databases** - convert existing incident reports into scenario JSON
- **Slack incident channels** - parse human SRE decisions from chat history

**Implementation plan:**

1. Create `shadow_mode.py` with `ShadowReplay` class
2. Add `POST /shadow/replay` endpoint that accepts an incident log JSON and creates a scenario
3. Add `POST /shadow/score` endpoint that compares agent actions against the real human timeline
4. Create an ingestion pipeline for PagerDuty webhook format
5. Add shadow mode scoring to the post-mortem report (human comparison column)

**Why this matters:** Shadow mode turns our environment from a training tool into an evaluation platform for production AI SRE agents. Companies can continuously test their AI agent against real incidents without any production risk. The human-AI gap measurement becomes ongoing, not a one-time benchmark.

## Connection to Broader Research

**Adversarial AI assessment:** The multi-agent architecture extends to adversarial scenarios where attack agents create incidents while defensive agents detect them. Related work: [Parity Swarm](https://parity-swarn-v2-2.vercel.app/) ([paper](https://apartresearch.com/project/parity-swarm-using-populationbased-social-simulation-to-discover-ai-safety-monitor-blind-spots-c9qc)).

**AI governance:** The post-mortem system, evidence board, and deterministic scoring provide an auditable record of AI decision-making, extensible to EU AI Act requirements for high-risk AI transparency (Article 13) and human oversight (Article 14).

**Enterprise RL:** The same architecture (scenario JSON, command processing, hybrid scoring, MCP tool discovery) adapts to IT helpdesk, SOC analysis, cloud cost optimization, database administration, and compliance auditing.
