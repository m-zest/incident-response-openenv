"""
Core SRE Incident Response Environment.

Implements the OpenEnv interface: reset(), step(), state().
Manages scenario lifecycle, processes agent commands, and computes rewards.
"""

import uuid
import random
from typing import Optional

from openenv.core.env_server import Environment

from ..models import SREAction, SREObservation, SREState, Alert
from .infrastructure import SimulatedCluster, load_scenarios
from .grader import compute_step_reward, compute_final_score


TASK_DEFINITIONS = [
    {
        "id": "easy",
        "name": "Single Alert Triage",
        "description": "A single service has a clear issue. Diagnose and fix it.",
        "difficulty": "easy",
        "max_steps": 10,
    },
    {
        "id": "medium",
        "name": "Correlated Multi-Service Failure",
        "description": "Multiple alerts firing. Trace the dependency chain to find the root cause.",
        "difficulty": "medium",
        "max_steps": 15,
    },
    {
        "id": "hard",
        "name": "Cascading Failure with Security Ambiguity",
        "description": "Complex cascading failure. Determine if it is an SRE issue or a security breach.",
        "difficulty": "hard",
        "max_steps": 20,
    },
]


class SREEnvironment(Environment):
    """
    On-Call SRE Simulator.

    The agent acts as a site reliability engineer responding to
    production incidents in a simulated microservices cluster.
    """

    def __init__(self):
        super().__init__()
        self._state = SREState()
        self._cluster: Optional[SimulatedCluster] = None
        self._scenarios = {
            "easy": load_scenarios("easy"),
            "medium": load_scenarios("medium"),
            "hard": load_scenarios("hard"),
        }

    def reset(self, task_id: str = "easy", scenario_index: int = -1) -> SREObservation:
        """
        Initialize a new incident episode.

        Args:
            task_id: Difficulty tier - "easy", "medium", or "hard"
            scenario_index: Specific scenario index, or -1 for random
        """
        if task_id not in self._scenarios:
            task_id = "easy"

        scenarios = self._scenarios[task_id]
        if scenario_index < 0 or scenario_index >= len(scenarios):
            scenario = random.choice(scenarios)
        else:
            scenario = scenarios[scenario_index]

        # Initialize the simulated cluster
        self._cluster = SimulatedCluster(scenario)

        # Initialize episode state
        self._state = SREState(
            episode_id=str(uuid.uuid4()),
            task_id=task_id,
            scenario_id=scenario["id"],
            step_count=0,
            max_steps=scenario["max_steps"],
            root_cause=scenario["root_cause"],
            initial_health=self._cluster.initial_health,
            current_health=self._cluster.health,
            optimal_steps=scenario["optimal_steps"],
            done=False,
        )

        # Build initial observation
        alerts = [
            Alert(
                service=a["service"],
                alert_type=a["alert_type"],
                severity=a["severity"],
                message=a["message"],
            )
            for a in self._cluster.get_active_alerts()
        ]

        initial_output = (
            f"=== INCIDENT ALERT ===\n"
            f"You are the on-call SRE engineer.\n"
            f"System health: {self._cluster.health:.0f}%\n"
            f"Active alerts: {len(alerts)}\n"
            f"\nDiagnose the issue, identify the root cause, and fix it.\n"
            f"Use the available commands to investigate and remediate.\n"
            f"Submit your root cause diagnosis when you've identified it.\n"
            f"\nThink step-by-step: analyze alerts, check logs and metrics,\n"
            f"trace the dependency chain, then take corrective action."
        )

        return SREObservation(
            output=initial_output,
            alerts=alerts,
            system_health=self._cluster.health,
            step_count=0,
            max_steps=self._state.max_steps,
            done=False,
            score=0.0,
        )

    def step(self, action: SREAction) -> SREObservation:
        """
        Process an agent action and return the resulting observation.
        """
        if self._cluster is None:
            return SREObservation(
                output="ERROR: Environment not initialized. Call reset() first.",
                system_health=0,
                step_count=0,
                max_steps=20,
                done=True,
                score=0.0,
            )

        if self._state.done:
            return SREObservation(
                output="Episode already ended. Call reset() to start a new one.",
                alerts=[],
                system_health=self._cluster.health,
                step_count=self._state.step_count,
                max_steps=self._state.max_steps,
                done=True,
                score=self._state.cumulative_reward,
            )

        # Increment step
        self._state.step_count += 1
        self._state.actions_taken.append(f"{action.command} {action.target}")

        # Check for destructive actions
        destructive_commands = ["delete_data", "drop_table", "format_disk", "rm_rf"]
        if action.command in destructive_commands:
            self._state.destructive_actions += 1

        # Track service health before action (for calibrated restraint scoring)
        service_was_healthy = False
        if action.target in self._cluster.services:
            service_was_healthy = self._cluster.services[action.target]["healthy"]

        # Execute the command on the simulated cluster
        if action.command == "submit_root_cause":
            output = self._cluster.execute_command(action.command, action.target, action.parameters)
        else:
            output = self._cluster.execute_command(action.command, action.target, action.parameters)

        # Apply time-based effects (e.g., malware respawning)
        self._cluster.tick()

        # Nudge agent to submit diagnosis after a successful fix
        if (action.command in ("restart_service", "rollback_deploy", "scale_up")
                and self._cluster.health >= 85 and self._cluster.resolved):
            output += (
                "\n\nSystem restored. Submit your root cause diagnosis with: "
                "submit_root_cause {description}"
            )

        # Update state from cluster
        self._state.current_health = self._cluster.health
        self._state.root_cause_found = self._cluster.root_cause_found
        self._state.root_cause_submitted = self._cluster.submitted_root_cause
        self._state.services_restarted = list(self._cluster.restarted_services)
        self._state.services_investigated = list(self._cluster.investigated_services)
        self._state.correct_services_investigated = list(self._cluster.correct_investigations)

        # Compute step reward
        is_correct_fix = (
            action.target == self._cluster.fix_target
            and action.command == self._cluster.fix_action
        )
        step_reward = compute_step_reward(
            command=action.command,
            target=action.target,
            root_cause_service=self._cluster.root_cause_service,
            service_was_healthy=service_was_healthy,
            is_correct_fix=is_correct_fix,
            is_root_cause_correct=self._cluster.root_cause_found,
        )
        self._state.cumulative_reward += step_reward

        # Check if episode should end
        episode_done = False
        if action.command == "submit_root_cause":
            episode_done = True
        elif self._state.step_count >= self._state.max_steps:
            episode_done = True
            output += "\n\nMAX STEPS REACHED. Episode ending."

        self._state.done = episode_done

        # Compute final score if done
        if episode_done:
            # If agent fixed the system but ran out of steps without
            # submitting root cause, give partial credit (omega=0.8)
            timed_out_resolved = (
                self._state.step_count >= self._state.max_steps
                and self._cluster.resolved
                and self._cluster.health >= 85
                and not self._state.root_cause_found
            )
            final_score = compute_final_score(
                initial_health=self._state.initial_health,
                final_health=self._state.current_health,
                root_cause_found=self._state.root_cause_found,
                root_cause_submitted=bool(self._state.root_cause_submitted),
                steps_taken=self._state.step_count,
                optimal_steps=self._state.optimal_steps,
                destructive_actions=self._state.destructive_actions,
                resolved=self._cluster.resolved,
                timed_out_resolved=timed_out_resolved,
            )
            self._state.cumulative_reward = final_score

        # Build observation
        alerts = [
            Alert(
                service=a["service"],
                alert_type=a["alert_type"],
                severity=a["severity"],
                message=a["message"],
            )
            for a in self._cluster.get_active_alerts()
        ]

        return SREObservation(
            output=output,
            alerts=alerts,
            system_health=self._cluster.health,
            step_count=self._state.step_count,
            max_steps=self._state.max_steps,
            done=self._state.done,
            score=self._state.cumulative_reward,
        )

    @property
    def state(self) -> SREState:
        """Return the current internal state (for grading, hidden from agent)."""
        return self._state

    def get_tasks(self) -> list[dict]:
        """Return task definitions for the /tasks endpoint."""
        return TASK_DEFINITIONS

    def get_grader_result(self) -> dict:
        """Return grading result for the /grader endpoint."""
        if not self._state.done:
            return {"error": "Episode not finished. Complete the episode first."}
        return {
            "task_id": self._state.task_id,
            "scenario_id": self._state.scenario_id,
            "score": self._state.cumulative_reward,
            "root_cause_found": self._state.root_cause_found,
            "steps_taken": self._state.step_count,
            "optimal_steps": self._state.optimal_steps,
            "health_initial": self._state.initial_health,
            "health_final": self._state.current_health,
            "destructive_actions": self._state.destructive_actions,
        }
