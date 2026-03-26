"""
Deterministic grading logic for the SRE environment.

Implements the scoring formula:
  S = max(0, (H_final - H_initial) / (100 - H_initial) * omega - phi - psi)

All scoring is based on objective system state. No LLM-as-judge.
"""


def compute_step_reward(
    command: str,
    target: str,
    root_cause_service: str,
    service_was_healthy: bool,
    is_correct_fix: bool,
    is_root_cause_correct: bool,
) -> float:
    """
    Compute the partial reward signal for a single step.
    Returns a float that gets added to cumulative reward.
    """
    reward = 0.0

    # Investigating the right service
    if command in ("check_logs", "get_metrics", "check_process_list", "check_network"):
        if target == root_cause_service:
            reward += 0.08  # Investigating the root cause service
        else:
            reward += 0.01  # Gathering info, but not the most relevant

    # Checking dependencies / graph analysis (always useful)
    elif command in ("check_dependencies", "get_dependency_graph", "trace_failure"):
        reward += 0.03

    # Listing alerts (useful first step)
    elif command == "list_alerts":
        reward += 0.02

    # Evidence board and runbook (neutral — tracking, not acting)
    elif command in ("add_note", "view_notes", "get_runbook"):
        reward += 0.0

    # Restarting services
    elif command == "restart_service":
        if is_correct_fix:
            reward += 0.25  # Correct remediation
        elif service_was_healthy:
            reward -= 0.05  # Penalize restarting healthy service (calibrated restraint)
        else:
            reward += 0.03  # Restarting a broken service, not the root cause

    # Scaling up
    elif command == "scale_up":
        if is_correct_fix:
            reward += 0.25
        else:
            reward += 0.01  # Minimal benefit

    # Rolling back
    elif command == "rollback_deploy":
        if is_correct_fix:
            reward += 0.25
        else:
            reward += 0.01

    # Killing a process
    elif command == "kill_process":
        if is_correct_fix:
            reward += 0.25  # Correct remediation (killed malicious process)
        # Penalty for killing legitimate processes handled via destructive_actions

    # Submitting root cause
    elif command == "submit_root_cause":
        if is_root_cause_correct:
            reward += 0.30  # Big bonus for correct diagnosis
        else:
            reward -= 0.10  # Penalty for wrong diagnosis

    return reward


def compute_final_score(
    initial_health: float,
    final_health: float,
    root_cause_found: bool,
    root_cause_submitted: bool,
    steps_taken: int,
    optimal_steps: int,
    destructive_actions: int,
    resolved: bool,
    timed_out_resolved: bool = False,
) -> float:
    """
    Compute the final episode score using the deterministic formula.

    S = max(0, (H_final - H_initial) / (100 - H_initial) * omega - phi - psi)

    Where:
      omega = 1.0 if root cause correctly identified
      omega = 0.8 if fixed and ran out of steps (partial credit)
      omega = 0.6 if fixed without diagnosis
      omega = 0.3 otherwise
      phi = 0.02 per step beyond optimal (capped at 0.3)
      psi = 0.15 per destructive action
    """
    # Health delta component
    if initial_health >= 100:
        health_ratio = 1.0
    else:
        health_ratio = max(0.0, (final_health - initial_health) / (100.0 - initial_health))

    # Omega: diagnostic multiplier
    if root_cause_found:
        omega = 1.0
    elif timed_out_resolved:
        omega = 0.8  # Fixed it, ran out of steps before diagnosing
    elif resolved:
        omega = 0.6  # Fixed it but didn't identify root cause
    else:
        omega = 0.3  # Neither fixed nor diagnosed

    # Phi: efficiency penalty
    excess_steps = max(0, steps_taken - optimal_steps)
    phi = min(0.3, excess_steps * 0.02)

    # Psi: destructive action penalty
    psi = destructive_actions * 0.15

    # Final score
    score = max(0.0, health_ratio * omega - phi - psi)
    return min(1.0, score)
