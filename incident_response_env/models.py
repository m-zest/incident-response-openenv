"""
Pydantic models for the Incident Response SRE Environment.

Defines the strict typing contract between the agent and the environment:
- SREAction: what the agent can do
- SREObservation: what the agent sees
- SREState: internal episode tracking
"""

from typing import Optional
from pydantic import BaseModel, Field


class SREAction(BaseModel):
    """Action that the agent sends to the environment each step."""

    command: str = Field(
        ...,
        description=(
            "The CLI command to execute. One of: "
            "check_logs, get_metrics, list_alerts, check_dependencies, "
            "restart_service, scale_up, rollback_deploy, "
            "check_process_list, check_network, submit_root_cause"
        ),
    )
    target: str = Field(
        default="",
        description="The service or resource to act on (e.g., 'cache-redis', 'payment-service').",
    )
    parameters: dict = Field(
        default_factory=dict,
        description="Optional parameters (e.g., {'lines': 50} for check_logs).",
    )


class Alert(BaseModel):
    """A single firing alert in the system."""

    service: str
    alert_type: str
    severity: str = Field(description="One of: critical, warning, info")
    message: str


class SREObservation(BaseModel):
    """Observation returned to the agent after each step."""

    output: str = Field(description="Textual result of the agent's last command.")
    alerts: list[Alert] = Field(
        default_factory=list, description="Currently firing alerts."
    )
    system_health: float = Field(
        description="Overall system health percentage 0-100."
    )
    step_count: int = Field(description="How many steps the agent has taken.")
    max_steps: int = Field(description="Maximum allowed steps for this task.")
    done: bool = Field(
        default=False, description="Whether the episode has ended."
    )
    score: float = Field(
        default=0.0, description="Current cumulative score 0.0-1.0."
    )
    available_commands: list[str] = Field(
        default_factory=lambda: [
            "check_logs {service}",
            "get_metrics {service}",
            "list_alerts",
            "check_dependencies {service}",
            "restart_service {service}",
            "scale_up {service}",
            "rollback_deploy {service}",
            "check_process_list {service}",
            "check_network {service}",
            "submit_root_cause {description}",
        ],
        description="Available commands the agent can use.",
    )


class SREState(BaseModel):
    """Internal state tracking for the episode (hidden from agent, used by grader)."""

    episode_id: str = ""
    task_id: str = Field(default="easy", description="Difficulty tier: easy, medium, hard")
    scenario_id: str = ""
    step_count: int = 0
    max_steps: int = 20
    root_cause: str = Field(default="", description="The hidden actual root cause.")
    root_cause_found: bool = False
    root_cause_submitted: str = ""
    initial_health: float = 0.0
    current_health: float = 0.0
    services_restarted: list[str] = Field(default_factory=list)
    services_investigated: list[str] = Field(default_factory=list)
    correct_services_investigated: list[str] = Field(default_factory=list)
    destructive_actions: int = 0
    optimal_steps: int = 3
    actions_taken: list[str] = Field(default_factory=list)
    cumulative_reward: float = 0.0
    done: bool = False
