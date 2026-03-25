"""
Client for the SRE Incident Response Environment.

Usage:
    from incident_response_env import SREEnv, SREAction

    with SREEnv(base_url="https://your-hf-space.hf.space").sync() as client:
        result = client.reset()
        result = client.step(SREAction(command="check_logs", target="server-3"))
"""

from openenv.core.env_client import EnvClient


class SREEnv(EnvClient):
    """Client for connecting to the SRE Incident Response environment."""
    pass
