#!/usr/bin/env python3
"""
Baseline inference script for the Incident Response SRE Environment.

Connects an LLM (via OpenAI-compatible API) to the environment and
runs it through all 3 task tiers, reporting scores.

Usage:
    # With Groq (free, Llama 3.3 70B):
    OPENAI_API_KEY=your-groq-key OPENAI_BASE_URL=https://api.groq.com/openai/v1 python baseline.py

    # With NVIDIA Nemotron (free tier):
    OPENAI_API_KEY=your-nvidia-key OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1 python baseline.py

    # With OpenAI:
    OPENAI_API_KEY=your-key python baseline.py
"""

import os
import json
import sys

from openai import OpenAI

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_response_env.models import SREAction
from incident_response_env.server.environment import SREEnvironment

# Configuration
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) on-call for a production microservices cluster.

You have been alerted to an incident. Your goal is to:
1. Analyze the firing alerts
2. Investigate by checking logs, metrics, and service health
3. Identify the root cause
4. Take corrective action to restore the system
5. Submit your root cause diagnosis

IMPORTANT INSTRUCTIONS:
- Think step-by-step before taking action
- Check logs and metrics of suspicious services BEFORE restarting anything
- Do NOT restart services blindly — investigate first
- Use check_process_list and check_network if you suspect a security issue
- When you have identified the root cause, use submit_root_cause to declare it

Available commands:
- check_logs {service} — View recent logs
- get_metrics {service} — View CPU, memory, disk, latency stats
- list_alerts — View all firing alerts
- check_dependencies {service} — See what depends on what
- restart_service {service} — Restart a service
- scale_up {service} — Add replicas
- rollback_deploy {service} — Roll back to previous version
- check_process_list {service} — View running processes (useful for detecting malware)
- check_network {service} — View network connections (useful for detecting attacks)
- submit_root_cause {description} — Declare your diagnosis (ends the episode)

Respond with ONLY a JSON object in this exact format:
{"command": "check_logs", "target": "service-name", "parameters": {}}
"""


def parse_action(response_text: str) -> SREAction:
    """Parse LLM response into an SREAction."""
    text = response_text.strip()

    # Try to extract JSON from the response
    # Handle cases where LLM wraps JSON in markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Find the first { and last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        data = json.loads(text)
        return SREAction(
            command=data.get("command", "list_alerts"),
            target=data.get("target", ""),
            parameters=data.get("parameters", {}),
        )
    except (json.JSONDecodeError, Exception):
        # Fallback: try to parse as a simple command
        return SREAction(command="list_alerts", target="", parameters={})


def run_episode(env: SREEnvironment, client: OpenAI, task_id: str, scenario_idx: int = 0) -> dict:
    """Run a single episode with the LLM agent."""
    obs = env.reset(task_id=task_id, scenario_index=scenario_idx)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"INCIDENT REPORT:\n\n{obs.output}\n\nAlerts:\n" +
         "\n".join(f"  [{a.severity.upper()}] {a.service}: {a.message}" for a in obs.alerts) +
         f"\n\nSystem Health: {obs.system_health:.0f}%\nMax Steps: {obs.max_steps}"}
    ]

    steps = 0
    while not obs.done and steps < obs.max_steps:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=1000,
                temperature=0.1,
            )
            assistant_msg = response.choices[0].message.content
        except Exception as e:
            print(f"  API error: {e}")
            break

        # Parse action from LLM response
        action = parse_action(assistant_msg)
        steps += 1

        print(f"  Step {steps}: {action.command} {action.target}")

        # Execute action
        obs = env.step(action)

        # Add to conversation history
        messages.append({"role": "assistant", "content": assistant_msg})
        messages.append({
            "role": "user",
            "content": f"Command result:\n{obs.output}\n\nSystem Health: {obs.system_health:.0f}% | "
                       f"Score: {obs.score:.2f} | Steps: {obs.step_count}/{obs.max_steps} | "
                       f"Active Alerts: {len(obs.alerts)}"
                       + ("\n\nEpisode complete." if obs.done else "\n\nWhat is your next action?")
        })

    return {
        "task_id": task_id,
        "scenario_id": env.state.scenario_id,
        "score": obs.score,
        "steps": steps,
        "root_cause_found": env.state.root_cause_found,
        "health_final": obs.system_health,
    }


def main():
    if not API_KEY:
        print("ERROR: Set OPENAI_API_KEY environment variable.")
        print("  For Groq (free):  export OPENAI_API_KEY=your-groq-key")
        print("  For NVIDIA:       export OPENAI_API_KEY=your-nvidia-key")
        sys.exit(1)

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    env = SREEnvironment()

    print(f"=== SRE Incident Response Baseline ===")
    print(f"Model: {MODEL}")
    print(f"API:   {BASE_URL}")
    print()

    all_results = {}
    for task_id in ["easy", "medium", "hard"]:
        scenarios = env._scenarios[task_id]
        task_scores = []

        print(f"--- Task: {task_id.upper()} ({len(scenarios)} scenarios) ---")
        for i, scenario in enumerate(scenarios):
            print(f"\n  Scenario {i+1}/{len(scenarios)}: {scenario['name']}")
            result = run_episode(env, client, task_id, i)
            task_scores.append(result["score"])
            print(f"  Result: score={result['score']:.2f}, steps={result['steps']}, "
                  f"root_cause={result['root_cause_found']}, health={result['health_final']:.0f}%")

        avg = sum(task_scores) / len(task_scores) if task_scores else 0
        all_results[task_id] = {
            "mean_score": round(avg, 2),
            "scores": [round(s, 2) for s in task_scores],
            "scenarios_tested": len(task_scores),
        }
        print(f"\n  {task_id.upper()} average: {avg:.2f}")

    print("\n=== BASELINE SUMMARY ===")
    for task_id, data in all_results.items():
        print(f"  {task_id:8s}: {data['mean_score']:.2f} (across {data['scenarios_tested']} scenarios)")

    # Save results
    with open("baseline_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to baseline_results.json")


if __name__ == "__main__":
    main()
