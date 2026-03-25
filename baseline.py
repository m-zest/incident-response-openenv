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
2. Investigate by checking logs, metrics, and dependencies of suspicious services
3. Identify the root cause service and failure mode
4. FIX the system first using restart_service, rollback_deploy, or scale_up
5. THEN submit your root cause diagnosis using submit_root_cause

CRITICAL WORKFLOW:
- Step 1: Check logs and metrics of the alerting services
- Step 2: Trace dependencies to find the actual root cause service
- Step 3: ALWAYS fix the system BEFORE submitting root cause (restart_service, rollback_deploy, or scale_up)
- Step 4: AFTER fixing, submit your root cause diagnosis
- If you suspect a security issue (unusual CPU, unknown processes), use check_process_list and check_network
- Do NOT restart healthy services — only restart the broken one
- Do NOT submit root cause without fixing first

Available commands:
- check_logs {service}
- get_metrics {service}
- list_alerts
- check_dependencies {service}
- restart_service {service}
- scale_up {service}
- rollback_deploy {service}
- check_process_list {service}
- check_network {service}
- submit_root_cause {description} — Put your diagnosis in the "target" field. This ENDS the episode.

RESPONSE FORMAT — respond with ONLY a JSON object, no other text:

Example 1 — check logs:
{"command": "check_logs", "target": "database-primary", "parameters": {}}

Example 2 — restart a broken service:
{"command": "restart_service", "target": "cache-redis", "parameters": {}}

Example 3 — rollback a bad deploy:
{"command": "rollback_deploy", "target": "api-gateway", "parameters": {}}

Example 4 — scale up overwhelmed workers:
{"command": "scale_up", "target": "worker-queue", "parameters": {}}

Example 5 — submit root cause (AFTER fixing):
{"command": "submit_root_cause", "target": "disk full on log-server causing write failures", "parameters": {}}

Example 6 — submit security root cause:
{"command": "submit_root_cause", "target": "crypto mining malware attack on payment-service", "parameters": {}}
"""


def parse_action(response_text: str) -> SREAction:
    """Parse LLM response into an SREAction."""
    text = (response_text or "").strip()

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
