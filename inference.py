#!/usr/bin/env python3
"""
Baseline inference script for the Incident Response SRE Environment.

Connects an LLM (via OpenAI-compatible API) to the environment and
runs it through all 4 task tiers, reporting scores.

STDOUT FORMAT (required by OpenEnv validator):
    [START] task=<name> env=incident-response-env model=<model>
    [STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=null
    [END] success=<true|false> steps=<n> score=<0.00> rewards=<r1,r2,...>

Usage:
    HF_TOKEN=your-key API_BASE_URL=https://integrate.api.nvidia.com/v1 python inference.py
"""

import argparse
import os
import json
import sys

from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from incident_response_env.models import SREAction
from incident_response_env.server.environment import SREEnvironment

API_KEY = os.environ.get("HF_TOKEN") or os.environ.get("API_KEY", "")
BASE_URL = os.environ.get("API_BASE_URL", "https://api.groq.com/openai/v1")
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
- Heavy services (database, redis) take 2 steps to restart — investigate other services while waiting
- Do NOT submit root cause without fixing first

Available commands:
- check_logs {service}
- get_metrics {service}
- list_alerts
- check_dependencies {service}
- get_dependency_graph
- trace_failure {service}
- restart_service {service}
- scale_up {service}
- rollback_deploy {service}
- kill_process {service} (parameters: {"pid": "1234"})
- check_process_list {service}
- check_network {service}
- add_note {text}
- view_notes
- get_runbook
- submit_root_cause {description}

RESPONSE FORMAT — respond with ONLY a JSON object, no other text:
{"command": "check_logs", "target": "database-primary", "parameters": {}}
{"command": "restart_service", "target": "cache-redis", "parameters": {}}
{"command": "submit_root_cause", "target": "disk full on log-server causing write failures", "parameters": {}}
"""


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
    before_sleep=lambda rs: print(f"  Rate limited. Retrying in {rs.next_action.sleep:.0f}s..."),
)
def call_llm(client, messages, model):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1024,
        temperature=0.2,
    )
    return response


def parse_action(response_text):
    text = (response_text or "").strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
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
        return SREAction(command="list_alerts", target="", parameters={})


def run_episode(env, client, task_id, scenario_idx=0):
    obs = env.reset(task_id=task_id, scenario_index=scenario_idx)

    print(f"[START] task={task_id} env=incident-response-env model={MODEL}", flush=True)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"INCIDENT REPORT:\n\n{obs.output}\n\nAlerts:\n" +
         "\n".join(f"  [{a.severity.upper()}] {a.service}: {a.message}" for a in obs.alerts) +
         f"\n\nSystem Health: {obs.system_health:.0f}%\nMax Steps: {obs.max_steps}"}
    ]

    steps = 0
    rewards = []

    while not obs.done and steps < obs.max_steps:
        try:
            response = call_llm(client, messages, MODEL)
            assistant_msg = response.choices[0].message.content
        except Exception as e:
            print(f"  API error (after retries): {e}")
            break

        action = parse_action(assistant_msg)
        steps += 1

        obs = env.step(action)

        step_reward = getattr(obs, 'reward', 0.0)
        rewards.append(step_reward)

        action_str = f"{action.command} {action.target}".strip()
        print(f"  Step {steps}: {action_str}")
        print(f"[STEP] step={steps} action={action_str} reward={step_reward:.2f} done={str(obs.done).lower()} error=null", flush=True)

        messages.append({"role": "assistant", "content": assistant_msg})
        messages.append({
            "role": "user",
            "content": f"Command result:\n{obs.output}\n\nSystem Health: {obs.system_health:.0f}% | "
                       f"Score: {obs.score:.2f} | Steps: {obs.step_count}/{obs.max_steps} | "
                       f"Active Alerts: {len(obs.alerts)}"
                       + ("\n\nEpisode complete." if obs.done else "\n\nWhat is your next action?")
        })

    root_cause_found = env.state.root_cause_found
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    final_score = max(0.01, min(0.99, obs.score))
    print(f"[END] success={str(root_cause_found).lower()} steps={steps} score={final_score:.2f} rewards={rewards_str}", flush=True)

    return {
        "task_id": task_id,
        "scenario_id": env.state.scenario_id,
        "score": obs.score,
        "steps": steps,
        "root_cause_found": root_cause_found,
        "health_final": obs.system_health,
        "rewards": rewards,
    }


def main():
    parser = argparse.ArgumentParser(description="SRE Incident Response Baseline")
    parser.add_argument("--task", type=str, default=None,
                        choices=["easy", "medium", "hard", "expert"],
                        help="Run only a specific difficulty tier (default: all)")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: Set HF_TOKEN or API_KEY environment variable.")
        print("  For Groq (free):  export HF_TOKEN=your-groq-key")
        print("  For NVIDIA:       export HF_TOKEN=your-nvidia-key")
        sys.exit(1)

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    env = SREEnvironment()

    tiers = [args.task] if args.task else ["easy", "medium", "hard", "expert"]

    print(f"=== SRE Incident Response Baseline ===")
    print(f"Model: {MODEL}")
    print(f"API:   {BASE_URL}")
    print(f"Tiers: {', '.join(tiers)}")
    print()

    all_results = {}
    for task_id in tiers:
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

    with open("baseline_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to baseline_results.json")


if __name__ == "__main__":
    main()
