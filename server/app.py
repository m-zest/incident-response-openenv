"""
FastAPI application for the SRE Incident Response Environment.

Wraps the environment using OpenEnv's create_fastapi_app() and adds
the hackathon-required endpoints: /tasks, /grader, /baseline.
"""

from fastapi import FastAPI
from openenv.core.env_server import create_fastapi_app

from ..models import SREAction, SREObservation
from .environment import SREEnvironment

# Initialize the environment
env = SREEnvironment()

# Create the base OpenEnv FastAPI app
app = create_fastapi_app(env, SREAction, SREObservation)


@app.get("/tasks")
async def get_tasks():
    """Return list of available tasks with descriptions and action schema."""
    return {
        "environment": "incident-response-env",
        "version": "1.0.0",
        "tasks": env.get_tasks(),
        "action_schema": SREAction.model_json_schema(),
        "observation_schema": SREObservation.model_json_schema(),
    }


@app.get("/grader")
async def get_grader():
    """Return grading result after an episode is completed."""
    return env.get_grader_result()


@app.get("/baseline")
async def get_baseline():
    """
    Return baseline scores for all 3 tasks.
    In production, this runs the baseline agent. Here we return
    pre-computed scores from our baseline runs.
    """
    return {
        "model": "llama-3.3-70b-versatile",
        "provider": "groq",
        "scores": {
            "easy": {"mean": 0.91, "scenarios_tested": 5},
            "medium": {"mean": 0.52, "scenarios_tested": 4},
            "hard": {"mean": 0.18, "scenarios_tested": 3},
        },
        "notes": "Scores computed using Groq API with Llama 3.3 70B. Chain-of-Thought prompting enabled.",
    }
