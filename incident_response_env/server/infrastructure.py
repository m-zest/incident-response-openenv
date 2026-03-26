"""
Simulated infrastructure engine for the SRE environment.

Loads scenarios from JSON, manages service states, and processes
agent commands against the simulated cluster.
"""

import json
import os
import random
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import networkx as nx

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


def load_scenarios(difficulty: str) -> list[dict]:
    """Load scenario definitions from JSON files."""
    path = SCENARIOS_DIR / f"{difficulty}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    with open(path) as f:
        return json.load(f)


# ── Dynamic Log Generator ─────────────────────────────────────────────────


class LogGenerator:
    """Template-based log generator. Seeded RNG for determinism within an episode."""

    def __init__(self, seed: str):
        self._rng = random.Random(seed)
        self._base_time = datetime(2026, 3, 25, 8, 0, 0)
        self._step = 0

    def _ts(self, offset_s: int = 0) -> str:
        t = self._base_time + timedelta(seconds=self._step * 30 + offset_s)
        return t.strftime("[%Y-%m-%dT%H:%M:%SZ]")

    def advance(self):
        self._step += 1

    def generate_degradation_log(self, service: str, metric: str, value: float) -> str:
        templates = [
            f"{self._ts()} WARN   {service}: {metric} degraded to {value:.0f}%",
            f"{self._ts(1)} WARN   Threshold breach on {service}: {metric}={value:.0f}%",
            f"{self._ts(2)} ERROR  {service} {metric} critical: {value:.0f}% (limit approaching)",
        ]
        return self._rng.choice(templates)

    def generate_cascade_log(self, source: str, target: str) -> str:
        templates = [
            f"{self._ts()} ERROR  {target}: upstream dependency {source} unhealthy, requests failing",
            f"{self._ts(1)} WARN   {target}: connection errors to {source}, circuit breaker triggered",
            f"{self._ts(2)} ERROR  {target}: timeout waiting for {source} response",
        ]
        return self._rng.choice(templates)

    def generate_alert_escalation(self, service: str, metric: str) -> str:
        return f"{self._ts()} CRITICAL  {service}: {metric} has crossed critical threshold"


# ── Simulated Cluster ──────────────────────────────────────────────────────


class SimulatedCluster:
    """
    A text-based simulation of a microservices cluster.
    All data is fake — Python dicts and strings.
    No real servers, no real infrastructure.
    """

    def __init__(self, scenario: dict, seed: int = None):
        self.scenario = scenario
        self.scenario_id = scenario["id"]
        self.root_cause = scenario["root_cause"]
        self.root_cause_service = scenario["root_cause_service"]
        self.root_cause_keywords = scenario.get("root_cause_keywords", [])
        self.fix_action = scenario["fix_action"]
        self.fix_target = scenario["fix_target"]
        self.special_fix = scenario.get("special_fix", None)
        self.malicious_pid = scenario.get("malicious_pid", None)
        self.restart_temporary = scenario.get("restart_temporary", False)
        self.restart_revert_steps = scenario.get("restart_revert_steps", 0)

        self.initial_health = float(scenario["initial_health"])
        self.health = float(scenario["initial_health"])
        self.health_on_fix = float(scenario["health_on_fix"])
        self.optimal_steps = scenario["optimal_steps"]
        self.max_steps = scenario["max_steps"]

        # Seeded RNG for reproducibility
        if seed is None:
            seed = random.randint(0, 999999)
        self._seed = seed
        self._rng = random.Random(seed)

        # Seeded log generator for dynamic logs
        self._log_gen = LogGenerator(str(seed))

        # Deep copy services so we can mutate
        self.services = {}
        for name, svc in scenario["services"].items():
            self.services[name] = {
                "status": svc["status"],
                "healthy": svc["healthy"],
                "logs": list(svc["logs"]),
                "metrics": dict(svc["metrics"]),
                "processes": list(svc.get("processes", [])),
                "network": list(svc.get("network", [])),
            }

        self.dependencies = dict(scenario.get("dependencies", {}))
        self.alerts = [dict(a) for a in scenario["alerts"]]

        # Red herring noise alerts (auto-resolve after N steps)
        self._noise_alerts = []
        for na in scenario.get("noise_alerts", []):
            alert = dict(na)
            alert["_ttl"] = alert.pop("auto_resolve_after", 3)
            self.alerts.append({
                "service": alert["service"],
                "alert_type": alert.get("alert_type", "noise"),
                "severity": alert["severity"].lower(),
                "message": alert["message"],
            })
            self._noise_alerts.append(alert)
        self.resolved = False
        self.root_cause_found = False
        self.submitted_root_cause = ""
        self.restarted_services: list[str] = []
        self.investigated_services: list[str] = []
        self.correct_investigations: list[str] = []
        self.destructive_actions = 0
        self.steps_since_restart = 0
        self._network_checked: set = set()

        # Evidence board for agent notes
        self.evidence_board: list[dict] = []
        self._current_step = 0

        # Build dependency graph with NetworkX
        self._dep_graph = nx.DiGraph()
        for svc in self.services:
            self._dep_graph.add_node(svc)
        for svc, deps in self.dependencies.items():
            for dep in deps:
                self._dep_graph.add_edge(svc, dep)  # svc depends on dep

    def get_active_alerts(self) -> list[dict]:
        """Return currently firing alerts."""
        return [a for a in self.alerts]

    def execute_command(self, command: str, target: str, parameters: dict) -> str:
        """Process an agent command and return text output."""

        if command == "check_logs":
            return self._check_logs(target, parameters)
        elif command == "get_metrics":
            return self._get_metrics(target)
        elif command == "list_alerts":
            return self._list_alerts()
        elif command == "check_dependencies":
            return self._check_dependencies(target)
        elif command == "restart_service":
            return self._restart_service(target)
        elif command == "scale_up":
            return self._scale_up(target, parameters)
        elif command == "rollback_deploy":
            return self._rollback_deploy(target)
        elif command == "kill_process":
            return self._kill_process(target, parameters)
        elif command == "check_process_list":
            return self._check_process_list(target)
        elif command == "check_network":
            return self._check_network(target)
        elif command == "add_note":
            return self._add_note(target)
        elif command == "view_notes":
            return self._view_notes()
        elif command == "get_dependency_graph":
            return self._get_dependency_graph()
        elif command == "trace_failure":
            return self._trace_failure(target)
        elif command == "get_runbook":
            return self._get_runbook()
        elif command == "submit_root_cause":
            return self._submit_root_cause(target, parameters)
        else:
            return (
                f"ERROR: Unknown command '{command}'. Available: "
                "check_logs, get_metrics, list_alerts, check_dependencies, "
                "restart_service, scale_up, rollback_deploy, kill_process, "
                "check_process_list, check_network, add_note, view_notes, "
                "get_dependency_graph, trace_failure, get_runbook, submit_root_cause."
            )

    # ── Investigation commands ─────────────────────────────────────────────

    def _check_logs(self, service: str, parameters: dict) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found. Available: {', '.join(self.services.keys())}"
        self.investigated_services.append(service)
        if service == self.root_cause_service:
            self.correct_investigations.append(service)
        lines = parameters.get("lines", 50)
        logs = self.services[service]["logs"][-lines:]
        return f"=== Logs for {service} (last {len(logs)} lines) ===\n" + "\n".join(logs)

    def _get_metrics(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found. Available: {', '.join(self.services.keys())}"
        self.investigated_services.append(service)
        if service == self.root_cause_service:
            self.correct_investigations.append(service)
        m = self.services[service]["metrics"]
        return (
            f"=== Metrics for {service} ===\n"
            f"  CPU:         {m['cpu']}%\n"
            f"  Memory:      {m['memory']}%\n"
            f"  Disk:        {m['disk']}%\n"
            f"  Latency:     {m['latency_ms']}ms\n"
            f"  Connections: {m['connections']}/{m['max_connections']}"
        )

    def _list_alerts(self) -> str:
        if not self.alerts:
            return "No active alerts. System healthy."
        lines = ["=== Active Alerts ==="]
        for a in self.alerts:
            lines.append(f"  [{a['severity'].upper():8s}] {a['service']}: {a['message']}")
        return "\n".join(lines)

    def _check_dependencies(self, service: str) -> str:
        if service not in self.dependencies and service not in self.services:
            return f"ERROR: Service '{service}' not found."
        deps = self.dependencies.get(service, [])
        dependents = [s for s, d in self.dependencies.items() if service in d]
        return (
            f"=== Dependencies for {service} ===\n"
            f"  Depends on:     {deps if deps else ['(none)']}\n"
            f"  Depended on by: {dependents if dependents else ['(none)']}"
        )

    def _check_process_list(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."
        self.investigated_services.append(service)
        if service == self.root_cause_service:
            self.correct_investigations.append(service)
        procs = self.services[service].get("processes", [])
        if not procs:
            return f"=== Process List for {service} ===\n  No processes running (service may be down)."
        return f"=== Process List for {service} ===\n" + "\n".join(f"  {p}" for p in procs)

    def _check_network(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."
        self.investigated_services.append(service)
        self._network_checked.add(service)
        if service == self.root_cause_service:
            self.correct_investigations.append(service)
        net = self.services[service].get("network", [])
        if not net:
            return f"=== Network Connections for {service} ===\n  No active connections."
        return f"=== Network Connections for {service} ===\n" + "\n".join(f"  {n}" for n in net)

    # ── Remediation commands ───────────────────────────────────────────────

    def _restart_service(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."

        self.restarted_services.append(service)

        if service == self.fix_target and self.fix_action == "restart_service":
            self.services[service]["healthy"] = True
            self.services[service]["status"] = "healthy"
            old_health = self.health
            self.health = self.health_on_fix
            self.alerts = [a for a in self.alerts if a["service"] != service]
            self.resolved = True
            return (
                f"Service '{service}' restarted successfully.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Alerts cleared for {service}."
            )
        elif service == self.fix_target and self.restart_temporary:
            old_health = self.health
            temp_health = self.scenario.get("health_on_restart", self.health + 20)
            self.health = min(100, temp_health)
            self.steps_since_restart = 0
            return (
                f"Service '{service}' restarted.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"WARNING: Alerts temporarily cleared but may recur."
            )
        elif self.services[service]["healthy"]:
            return (
                f"Service '{service}' restarted (was already healthy).\n"
                f"No change in system health: {self.health:.0f}%\n"
                f"WARNING: Unnecessary restart of a healthy service."
            )
        else:
            self.services[service]["healthy"] = True
            old_health = self.health
            self.health = min(100, self.health + 5)
            return (
                f"Service '{service}' restarted.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Some symptoms may persist if root cause is elsewhere."
            )

    def _scale_up(self, service: str, parameters: dict) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."
        replicas = parameters.get("replicas", 3)

        if service == self.fix_target and self.fix_action == "scale_up":
            old_health = self.health
            self.health = self.health_on_fix
            self.resolved = True
            self.alerts = [a for a in self.alerts if a["service"] != service]
            return (
                f"Scaled {service} from 2 to {replicas} replicas.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Processing backlog clearing."
            )
        else:
            return (
                f"Scaled {service} to {replicas} replicas.\n"
                f"Minimal effect on system health: {self.health:.0f}%"
            )

    def _rollback_deploy(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."

        if service == self.fix_target and self.fix_action == "rollback_deploy":
            self.services[service]["healthy"] = True
            self.services[service]["status"] = "healthy"
            old_health = self.health
            self.health = self.health_on_fix
            self.resolved = True
            self.alerts = [a for a in self.alerts if a["service"] != service]
            return (
                f"Rolled back {service} to previous stable version.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Alerts cleared for {service}."
            )
        else:
            return (
                f"Rolled back {service} to previous version.\n"
                f"No significant effect. System health: {self.health:.0f}%"
            )

    def _kill_process(self, service: str, parameters: dict) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."
        pid = str(parameters.get("pid", ""))
        if not pid:
            return "ERROR: No PID specified. Usage: kill_process {service} with parameters: {\"pid\": \"1234\"}"

        if self.malicious_pid and pid == str(self.malicious_pid) and service == self.fix_target:
            # Require check_network on this service before kill_process works
            if service not in self._network_checked:
                return (
                    f"Cannot kill PID {pid} on {service}.\n"
                    f"ERROR: You must investigate network connections first "
                    f"(check_network {service}) to confirm the threat before "
                    f"terminating processes."
                )
            procs = self.services[service].get("processes", [])
            self.services[service]["processes"] = [
                p for p in procs if f"PID {pid}" not in p
            ]
            net = self.services[service].get("network", [])
            self.services[service]["network"] = [
                n for n in net if "10.0.1." in n.split("->")[-1] or "LISTEN" in n
            ]
            self.services[service]["healthy"] = True
            self.services[service]["status"] = "healthy"
            old_health = self.health
            self.health = self.health_on_fix
            self.resolved = True
            self.restart_temporary = False
            self.alerts = [a for a in self.alerts if a["service"] != service]
            return (
                f"Killed process PID {pid} on {service}.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Malicious process terminated. Service restored."
            )
        else:
            found = any(f"PID {pid}" in p for p in self.services[service].get("processes", []))
            if found:
                self.destructive_actions += 1
                return (
                    f"Killed process PID {pid} on {service}.\n"
                    f"WARNING: Killed a legitimate process. Service may be degraded.\n"
                    f"System health: {self.health:.0f}%"
                )
            else:
                return f"ERROR: Process PID {pid} not found on {service}."

    # ── Evidence board ─────────────────────────────────────────────────────

    def _add_note(self, text: str) -> str:
        if not text.strip():
            return "ERROR: Empty note. Usage: add_note {your observation or hypothesis}"
        note = {"step": self._current_step, "text": text.strip()}
        self.evidence_board.append(note)
        return f"Note saved at step {self._current_step}: \"{text.strip()}\""

    def _view_notes(self) -> str:
        if not self.evidence_board:
            return "=== Evidence Board ===\n  No notes recorded yet. Use add_note to save observations."
        lines = ["=== Evidence Board ==="]
        for n in self.evidence_board:
            lines.append(f"  [Step {n['step']}] {n['text']}")
        return "\n".join(lines)

    # ── Dependency graph (NetworkX) ────────────────────────────────────────

    def _get_dependency_graph(self) -> str:
        lines = ["=== Dependency Graph ==="]
        lines.append(f"  Services: {len(self._dep_graph.nodes)}")
        lines.append(f"  Dependencies: {len(self._dep_graph.edges)}")
        lines.append("")

        # Full tree
        lines.append("  Dependency tree:")
        for svc in sorted(self._dep_graph.nodes):
            deps = list(self._dep_graph.successors(svc))
            dependents = list(self._dep_graph.predecessors(svc))
            status = self.services.get(svc, {}).get("status", "unknown")
            marker = "x" if status in ("critical", "degraded", "down") else "o"
            lines.append(f"    [{marker}] {svc} ({status})")
            if deps:
                lines.append(f"        depends on: {', '.join(deps)}")
            if dependents:
                lines.append(f"        depended on by: {', '.join(dependents)}")

        # Most critical service by in-degree (most things depend on it)
        lines.append("")
        in_degrees = sorted(
            self._dep_graph.in_degree(), key=lambda x: x[1], reverse=True
        )
        if in_degrees and in_degrees[0][1] > 0:
            top = in_degrees[0]
            lines.append(f"  Highest impact service: {top[0]} ({top[1]} dependents)")

        return "\n".join(lines)

    def _trace_failure(self, service: str) -> str:
        if service not in self._dep_graph:
            return f"ERROR: Service '{service}' not found in dependency graph."

        # Upstream: what this service needs (follow outgoing edges)
        upstream = set()
        for node in nx.descendants(self._dep_graph, service):
            upstream.add(node)

        # Downstream: what breaks if this service fails (follow incoming edges)
        reverse = self._dep_graph.reverse()
        downstream = set()
        for node in nx.descendants(reverse, service):
            downstream.add(node)

        # Blast radius
        blast = downstream | {service}

        # Check health of upstream deps
        unhealthy_upstream = []
        for u in upstream:
            svc = self.services.get(u, {})
            if not svc.get("healthy", True):
                unhealthy_upstream.append(u)

        lines = [f"=== Failure Trace for {service} ==="]
        lines.append(f"  Upstream dependencies: {sorted(upstream) if upstream else ['(none)']}")
        lines.append(f"  Downstream dependents: {sorted(downstream) if downstream else ['(none)']}")
        lines.append(f"  Blast radius: {len(blast)} service(s)")
        if unhealthy_upstream:
            lines.append(f"  UNHEALTHY upstream: {sorted(unhealthy_upstream)}")
            lines.append(f"  -> Root cause may be in: {', '.join(sorted(unhealthy_upstream))}")
        else:
            lines.append(f"  All upstream dependencies healthy.")

        return "\n".join(lines)

    # ── Runbook ─────────────────────────────────────────────────────────────

    def _get_runbook(self) -> str:
        runbook = self.scenario.get("runbook", [])
        if not runbook:
            return "=== Runbook ===\n  No standard operating procedure available for this incident type."
        lines = [f"=== Runbook: {self.scenario.get('name', 'Incident')} ==="]
        for step in runbook:
            lines.append(f"  {step}")
        lines.append("\n  Follow these steps in order for optimal resolution.")
        return "\n".join(lines)

    # ── Root cause submission ──────────────────────────────────────────────

    def _submit_root_cause(self, description: str, parameters: dict = None) -> str:
        parts = [description]
        if parameters:
            for key in ("description", "reason", "root_cause", "diagnosis", "text"):
                if key in parameters and parameters[key]:
                    parts.append(str(parameters[key]))
        merged = " ".join(p for p in parts if p)

        self.submitted_root_cause = merged
        desc_lower = merged.lower()
        matches = sum(1 for kw in self.root_cause_keywords if kw.lower() in desc_lower)
        if matches >= 2 or self.root_cause.lower() in desc_lower:
            self.root_cause_found = True
            if not self.resolved:
                self.health = self.health_on_fix
                self.resolved = True
            return (
                f"Root cause accepted: '{merged}'\n"
                f"Correct diagnosis. System health restored to {self.health:.0f}%."
            )
        elif matches >= 1:
            self.root_cause_found = True
            if not self.resolved:
                self.health = self.health_on_fix
                self.resolved = True
            return (
                f"Root cause accepted: '{merged}'\n"
                f"Diagnosis recognized. System health restored to {self.health:.0f}%."
            )
        else:
            self.root_cause_found = False
            return (
                f"Root cause submitted: '{merged}'\n"
                f"Incorrect diagnosis. The actual issue was not identified."
            )

    # ── Time-evolving state ────────────────────────────────────────────────

    def tick(self):
        """Called each step. Handles malware respawn AND progressive degradation."""
        self._current_step += 1
        self._log_gen.advance()

        # Auto-resolve noise alerts
        for na in self._noise_alerts:
            na["_ttl"] -= 1
            if na["_ttl"] <= 0:
                self.alerts = [a for a in self.alerts
                               if not (a["service"] == na["service"] and a["message"] == na["message"])]
        self._noise_alerts = [na for na in self._noise_alerts if na["_ttl"] > 0]

        # Malware respawn logic
        if self.restart_temporary and self.steps_since_restart >= 0:
            self.steps_since_restart += 1
            if self.steps_since_restart >= self.restart_revert_steps and not self.root_cause_found:
                if self.health > self.initial_health + 10:
                    self.health = max(self.initial_health, self.health - 15)
                    if not self.alerts:
                        for a in self.scenario["alerts"]:
                            self.alerts.append(dict(a))

        # Progressive degradation: if root cause not fixed, things get worse
        if not self.resolved and self._current_step > 2:
            rc_svc = self.services.get(self.root_cause_service)
            if rc_svc and not rc_svc["healthy"]:
                # Degrade root cause service metrics
                m = rc_svc["metrics"]
                degrade = min(3, self._current_step * 0.5)
                if m["cpu"] < 100:
                    m["cpu"] = min(100, m["cpu"] + degrade)
                if m["latency_ms"] < 60000:
                    m["latency_ms"] = int(m["latency_ms"] * 1.08)

                # Overall health degrades
                self.health = max(5, self.health - 1.5)

                # Append dynamic degradation log
                rc_svc["logs"].append(
                    self._log_gen.generate_degradation_log(
                        self.root_cause_service, "CPU", m["cpu"]
                    )
                )

                # Cascade to dependents after step 4
                if self._current_step > 4:
                    reverse = self._dep_graph.reverse()
                    for dep in nx.descendants(reverse, self.root_cause_service):
                        dep_svc = self.services.get(dep)
                        if dep_svc:
                            dep_m = dep_svc["metrics"]
                            dep_m["latency_ms"] = int(dep_m["latency_ms"] * 1.05)
                            self.health = max(5, self.health - 0.5)
                            dep_svc["logs"].append(
                                self._log_gen.generate_cascade_log(
                                    self.root_cause_service, dep
                                )
                            )

                # Escalate alerts after step 5
                if self._current_step == 5:
                    for a in self.alerts:
                        if a["severity"] == "warning":
                            a["severity"] = "critical"
                            a["message"] += " [ESCALATED]"
