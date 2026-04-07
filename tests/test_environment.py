"""
Tests for the SRE Incident Response Environment.

Validates:
- Grader determinism (same inputs = same outputs always)
- Environment state transitions
- Scenario loading
- Action processing
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_response_env.models import SREAction
from incident_response_env.server.environment import SREEnvironment
from incident_response_env.server.grader import compute_final_score, compute_step_reward


class TestGraderDeterminism:
    """Verify that identical inputs always produce identical scores."""

    def test_same_inputs_same_score(self):
        score1 = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        score2 = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        assert score1 == score2, f"Scores differ: {score1} vs {score2}"

    def test_perfect_score(self):
        score = compute_final_score(40, 100, True, True, 3, 3, 0, True)
        assert score == 0.99, f"Expected 0.99, got {score}"

    def test_zero_progress(self):
        score = compute_final_score(40, 40, False, False, 10, 3, 0, False)
        assert score == 0.01, f"Expected 0.01, got {score}"

    def test_efficiency_penalty(self):
        optimal = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        slow = compute_final_score(40, 95, True, True, 13, 3, 0, True)
        assert slow < optimal, "Slow path should score lower"

    def test_destructive_penalty(self):
        clean = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        destructive = compute_final_score(40, 95, True, True, 3, 3, 2, True)
        assert destructive < clean, "Destructive actions should reduce score"

    def test_no_root_cause_penalty(self):
        with_rc = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        without_rc = compute_final_score(40, 95, False, False, 3, 3, 0, True)
        assert without_rc < with_rc, "Missing root cause should score lower"

    def test_score_bounded(self):
        score = compute_final_score(40, 95, True, True, 3, 3, 0, True)
        assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"

        score2 = compute_final_score(40, 40, False, False, 50, 3, 5, False)
        assert 0.0 <= score2 <= 1.0, f"Score out of bounds: {score2}"


class TestStepRewards:
    """Verify partial reward signals."""

    def test_investigating_root_cause(self):
        reward = compute_step_reward("check_logs", "server-3", "server-3", False, False, False)
        assert reward == 0.08

    def test_investigating_wrong_service(self):
        reward = compute_step_reward("check_logs", "frontend", "server-3", False, False, False)
        assert reward == 0.01

    def test_correct_fix(self):
        reward = compute_step_reward("restart_service", "server-3", "server-3", False, True, False)
        assert reward == 0.25

    def test_restarting_healthy_service(self):
        reward = compute_step_reward("restart_service", "frontend", "server-3", True, False, False)
        assert reward == -0.05

    def test_correct_root_cause_submission(self):
        reward = compute_step_reward("submit_root_cause", "disk full", "server-3", False, False, True)
        assert reward == 0.30

    def test_wrong_root_cause_submission(self):
        reward = compute_step_reward("submit_root_cause", "wrong cause", "server-3", False, False, False)
        assert reward == -0.10


class TestEnvironment:
    """Test the full environment lifecycle."""

    def test_reset_returns_observation(self):
        env = SREEnvironment()
        obs = env.reset(task_id="easy", scenario_index=0)
        assert obs.system_health > 0
        assert obs.system_health < 100
        assert len(obs.alerts) > 0
        assert obs.done is False
        assert obs.step_count == 0

    def test_step_processes_action(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        action = SREAction(command="list_alerts")
        obs = env.step(action)
        assert obs.step_count == 1
        assert "Alert" in obs.output or "alert" in obs.output.lower()

    def test_check_logs_returns_text(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        action = SREAction(command="check_logs", target="log-server")
        obs = env.step(action)
        assert "Logs for" in obs.output
        assert len(obs.output) > 50

    def test_episode_ends_on_max_steps(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        for _ in range(20):
            if env.state.done:
                break
            obs = env.step(SREAction(command="list_alerts"))
        assert env.state.done is True

    def test_submit_root_cause_ends_episode(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        obs = env.step(SREAction(command="submit_root_cause", target="disk full on log-server"))
        assert obs.done is True
        assert obs.score > 0

    def test_correct_fix_restores_health(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        initial_health = env.state.current_health
        obs = env.step(SREAction(command="restart_service", target="log-server"))
        assert obs.system_health > initial_health

    def test_wrong_fix_no_improvement(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        initial_health = env.state.current_health
        obs = env.step(SREAction(command="restart_service", target="frontend"))
        # Restarting a healthy service should not significantly help
        assert obs.system_health <= initial_health + 10

    def test_all_tasks_loadable(self):
        env = SREEnvironment()
        for task_id in ["easy", "medium", "hard", "expert"]:
            obs = env.reset(task_id=task_id, scenario_index=0)
            assert obs.system_health > 0
            assert len(obs.alerts) > 0

    def test_tasks_endpoint(self):
        env = SREEnvironment()
        tasks = env.get_tasks()
        assert len(tasks) == 4
        assert tasks[0]["id"] == "easy"
        assert tasks[1]["id"] == "medium"
        assert tasks[2]["id"] == "hard"
        assert tasks[3]["id"] == "expert"

    def test_grader_endpoint_before_done(self):
        env = SREEnvironment()
        env.reset(task_id="easy")
        result = env.get_grader_result()
        assert "error" in result

    def test_grader_endpoint_after_done(self):
        env = SREEnvironment()
        env.reset(task_id="easy", scenario_index=0)
        env.step(SREAction(command="submit_root_cause", target="disk full"))
        result = env.get_grader_result()
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0

    def test_deterministic_replay(self):
        """Same scenario + same actions = same final score. Critical for eval."""
        env = SREEnvironment()

        # Run 1
        env.reset(task_id="easy", scenario_index=0)
        env.step(SREAction(command="check_logs", target="log-server"))
        obs1 = env.step(SREAction(command="restart_service", target="log-server"))
        score1 = obs1.score

        # Run 2 (identical)
        env.reset(task_id="easy", scenario_index=0)
        env.step(SREAction(command="check_logs", target="log-server"))
        obs2 = env.step(SREAction(command="restart_service", target="log-server"))
        score2 = obs2.score

        assert score1 == score2, f"Non-deterministic: {score1} vs {score2}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
