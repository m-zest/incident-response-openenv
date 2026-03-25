"""
Simulated infrastructure engine for the SRE environment.

Loads scenarios from JSON, manages service states, and processes
agent commands against the simulated cluster.
"""

import json
import os
import random
from pathlib import Path
from typing import Optional

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


def load_scenarios(difficulty: str) -> list[dict]:
    """Load scenario definitions from JSON files."""
    path = SCENARIOS_DIR / f"{difficulty}.json"
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    with open(path) as f:
        return json.load(f)


class SimulatedCluster:
    """
    A text-based simulation of a microservices cluster.
    All data is fake — Python dicts and strings.
    No real servers, no real infrastructure.
    """

    def __init__(self, scenario: dict):
        self.scenario = scenario
        self.scenario_id = scenario["id"]
        self.root_cause = scenario["root_cause"]
        self.root_cause_service = scenario["root_cause_service"]
        self.root_cause_keywords = scenario.get("root_cause_keywords", [])
        self.fix_action = scenario["fix_action"]
        self.fix_target = scenario["fix_target"]
        self.special_fix = scenario.get("special_fix", None)
        self.restart_temporary = scenario.get("restart_temporary", False)
        self.restart_revert_steps = scenario.get("restart_revert_steps", 0)

        self.initial_health = float(scenario["initial_health"])
        self.health = float(scenario["initial_health"])
        self.health_on_fix = float(scenario["health_on_fix"])
        self.optimal_steps = scenario["optimal_steps"]
        self.max_steps = scenario["max_steps"]

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
        self.resolved = False
        self.root_cause_found = False
        self.submitted_root_cause = ""
        self.restarted_services: list[str] = []
        self.investigated_services: list[str] = []
        self.correct_investigations: list[str] = []
        self.destructive_actions = 0
        self.steps_since_restart = 0

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
        elif command == "check_process_list":
            return self._check_process_list(target)
        elif command == "check_network":
            return self._check_network(target)
        elif command == "submit_root_cause":
            return self._submit_root_cause(target, parameters)
        else:
            return f"ERROR: Unknown command '{command}'. Use list_alerts, check_logs, get_metrics, check_dependencies, restart_service, scale_up, rollback_deploy, check_process_list, check_network, or submit_root_cause."

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

    def _restart_service(self, service: str) -> str:
        if service not in self.services:
            return f"ERROR: Service '{service}' not found."

        self.restarted_services.append(service)

        # If this is the correct fix target
        if service == self.fix_target and self.fix_action == "restart_service":
            self.services[service]["healthy"] = True
            self.services[service]["status"] = "healthy"
            old_health = self.health
            self.health = self.health_on_fix
            # Clear related alerts
            self.alerts = [a for a in self.alerts if a["service"] != service]
            self.resolved = True
            return (
                f"Service '{service}' restarted successfully.\n"
                f"System health: {old_health:.0f}% -> {self.health:.0f}%\n"
                f"Alerts cleared for {service}."
            )
        # If restart is a temporary fix (e.g., crypto-miner scenario)
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
        # Restarting a healthy service (penalty-worthy)
        elif self.services[service]["healthy"]:
            return (
                f"Service '{service}' restarted (was already healthy).\n"
                f"No change in system health: {self.health:.0f}%\n"
                f"WARNING: Unnecessary restart of a healthy service."
            )
        else:
            # Restarting a non-root-cause unhealthy service
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
        if service == self.root_cause_service:
            self.correct_investigations.append(service)
        net = self.services[service].get("network", [])
        if not net:
            return f"=== Network Connections for {service} ===\n  No active connections."
        return f"=== Network Connections for {service} ===\n" + "\n".join(f"  {n}" for n in net)

    def _submit_root_cause(self, description: str, parameters: dict = None) -> str:
        # Merge target string with any description/reason in parameters
        # LLMs sometimes send: {"command": "submit_root_cause", "target": "", "parameters": {"description": "..."}}
        parts = [description]
        if parameters:
            for key in ("description", "reason", "root_cause", "diagnosis", "text"):
                if key in parameters and parameters[key]:
                    parts.append(str(parameters[key]))
        merged = " ".join(p for p in parts if p)

        self.submitted_root_cause = merged
        # Check if the description contains root cause keywords
        desc_lower = merged.lower()
        matches = sum(1 for kw in self.root_cause_keywords if kw.lower() in desc_lower)
        if matches >= 2 or self.root_cause.lower() in desc_lower:
            # Fully correct: 2+ keywords or exact root cause string
            self.root_cause_found = True
            if not self.resolved:
                self.health = self.health_on_fix
                self.resolved = True
            return (
                f"Root cause accepted: '{merged}'\n"
                f"Correct diagnosis. System health restored to {self.health:.0f}%."
            )
        elif matches >= 1:
            # Partially correct but lenient: 1 keyword is enough to accept
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

    def tick(self):
        """Called each step to handle time-based effects (e.g., malware respawning)."""
        if self.restart_temporary and self.steps_since_restart >= 0:
            self.steps_since_restart += 1
            if self.steps_since_restart >= self.restart_revert_steps and not self.root_cause_found:
                # Malware respawns, health degrades again
                if self.health > self.initial_health + 10:
                    self.health = max(self.initial_health, self.health - 15)
                    # Re-add alerts
                    if not self.alerts:
                        for a in self.scenario["alerts"]:
                            self.alerts.append(dict(a))
