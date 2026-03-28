"""
HTTP integration tests for the SRE Incident Response Environment API.

Tests all REST endpoints using FastAPI's TestClient.
Covers both OpenEnv standard endpoints (/reset, /step, /state, /health)
and custom endpoints (/web/reset, /web/step, /env/state, /tasks).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from incident_response_env.server.app import app


client = TestClient(app)


class TestHealthEndpoint:

    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_health_reports_healthy(self):
        response = client.get("/health")
        data = response.json()
        assert data["status"] in ("ok", "healthy")


class TestTasksEndpoint:

    def test_tasks_returns_200(self):
        response = client.get("/tasks")
        assert response.status_code == 200

    def test_tasks_returns_four_tiers(self):
        response = client.get("/tasks")
        data = response.json()
        assert len(data["tasks"]) == 4
        task_ids = [t["id"] for t in data["tasks"]]
        assert task_ids == ["easy", "medium", "hard", "expert"]

    def test_tasks_includes_schemas(self):
        response = client.get("/tasks")
        data = response.json()
        assert "action_schema" in data
        assert "observation_schema" in data


class TestEnvStateEndpoint:

    def test_env_state_returns_200(self):
        response = client.get("/env/state")
        assert response.status_code == 200

    def test_env_state_has_required_fields(self):
        response = client.get("/env/state")
        data = response.json()
        assert "task_id" in data
        assert "step_count" in data
        assert "done" in data
        assert "current_health" in data

    def test_env_state_reflects_reset(self):
        client.post("/web/reset", json={"task_id": "medium", "scenario_index": 0})
        response = client.get("/env/state")
        data = response.json()
        assert data["task_id"] == "medium"
        assert data["done"] is False


class TestOpenEnvResetEndpoint:

    def test_reset_returns_200(self):
        response = client.post("/reset", json={"task_id": "easy", "scenario_index": 0})
        assert response.status_code == 200

    def test_reset_returns_observation_wrapper(self):
        response = client.post("/reset", json={"task_id": "easy", "scenario_index": 0})
        data = response.json()
        assert "observation" in data
        assert "done" in data
        assert data["done"] is False
        obs = data["observation"]
        assert "output" in obs
        assert obs["system_health"] > 0


class TestOpenEnvStepEndpoint:

    def test_step_accepts_action_wrapper(self):
        response = client.post("/step", json={
            "action": {
                "command": "list_alerts",
                "target": "",
                "parameters": {}
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "observation" in data
        assert "output" in data["observation"]


class TestWebEndpoints:

    def test_web_reset(self):
        response = client.post("/web/reset", json={"task_id": "easy", "scenario_index": 0})
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert "services" in data

    def test_web_step(self):
        client.post("/web/reset", json={"task_id": "easy", "scenario_index": 0})
        response = client.post("/web/step", json={
            "command": "check_logs",
            "target": "log-server",
            "parameters": {}
        })
        assert response.status_code == 200
        data = response.json()
        assert "output" in data
        assert "evidence_notes" in data

    def test_web_step_submit_returns_grader(self):
        client.post("/web/reset", json={"task_id": "easy", "scenario_index": 0})
        response = client.post("/web/step", json={
            "command": "submit_root_cause",
            "target": "disk full on log-server",
            "parameters": {}
        })
        data = response.json()
        assert data["done"] is True
        assert data["grader"] is not None
        assert "score" in data["grader"]


class TestFullEpisode:

    def test_reset_investigate_fix_submit(self):
        client.post("/web/reset", json={"task_id": "easy", "scenario_index": 0})

        response = client.post("/web/step", json={
            "command": "check_logs",
            "target": "log-server",
            "parameters": {}
        })
        data = response.json()
        assert data["done"] is False
        assert "Logs for" in data["output"]

        response = client.post("/web/step", json={
            "command": "restart_service",
            "target": "log-server",
            "parameters": {}
        })
        data = response.json()
        assert data["system_health"] > 55

        response = client.post("/web/step", json={
            "command": "submit_root_cause",
            "target": "disk full on log-server",
            "parameters": {}
        })
        data = response.json()
        assert data["done"] is True
        assert data["score"] > 0.5
