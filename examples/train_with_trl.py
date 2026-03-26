"""
Minimal example: connecting the SRE Incident Response Environment to
HuggingFace TRL's GRPOTrainer for reinforcement learning.

This is a reference implementation showing researchers how to use the
environment for RL training. Actual training requires GPU resources and
is not part of the hackathon submission.

Requirements:
    pip install trl transformers torch incident-response-env
"""

from incident_response_env.server.environment import SREEnvironment
from incident_response_env.models import SREAction


def rollout(env: SREEnvironment, policy_fn, task_id: str = "easy") -> dict:
    """Run one episode. The policy_fn takes an observation string and returns an action dict."""

    obs = env.reset(task_id=task_id)
    trajectory = []

    while not obs.done:
        # Policy sees the text output + alerts, decides an action
        action_dict = policy_fn(obs.output, [a.model_dump() for a in obs.alerts])
        action = SREAction(**action_dict)

        obs = env.step(action)
        trajectory.append({
            "action": action_dict,
            "reward": obs.score,
            "done": obs.done,
        })

    # Final score from the deterministic grader becomes the RL reward
    return {"score": obs.score, "steps": len(trajectory), "trajectory": trajectory}


# ── TRL integration sketch ─────────────────────────────────────────────

def build_reward_fn(env: SREEnvironment):
    """Wraps the environment grader as a TRL-compatible reward function.

    GRPOTrainer expects: reward_fn(completions: list[str]) -> list[float]
    Each completion is the model's full response for one episode.
    """

    def reward_fn(completions: list[str]) -> list[float]:
        rewards = []
        for completion in completions:
            # Parse the model's multi-step plan from its completion
            # (In practice, you'd parse JSON actions from each line)
            env.reset(task_id="easy", seed=42)
            # ... execute parsed actions ...
            rewards.append(env.state.cumulative_reward)
        return rewards

    return reward_fn


if __name__ == "__main__":
    # Quick demo: random policy
    import random

    env = SREEnvironment()
    commands = ["check_logs", "get_metrics", "list_alerts", "check_dependencies"]
    services = ["frontend", "api-gateway", "database-primary", "cache-redis"]

    def random_policy(output, alerts):
        cmd = random.choice(commands)
        target = random.choice(services) if cmd != "list_alerts" else ""
        return {"command": cmd, "target": target, "parameters": {}}

    result = rollout(env, random_policy, task_id="easy")
    print(f"Random policy score: {result['score']:.2f} in {result['steps']} steps")

    # To use with TRL GRPOTrainer:
    #
    # from trl import GRPOTrainer, GRPOConfig
    # from transformers import AutoModelForCausalLM, AutoTokenizer
    #
    # model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.1-8B")
    # tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B")
    #
    # trainer = GRPOTrainer(
    #     model=model,
    #     reward_funcs=build_reward_fn(env),
    #     config=GRPOConfig(output_dir="sre-agent", num_train_epochs=3),
    #     tokenizer=tokenizer,
    # )
    # trainer.train()
