# Contributing to SRE Incident Response Environment

## Adding New Scenarios

Scenarios are JSON-driven — no code changes needed.

1. Create a new entry in `incident_response_env/scenarios/{tier}.json`
2. Define: `id`, `name`, `root_cause`, `services`, `alerts`, `logs`, `metrics`, `optimal_steps`, `max_steps`
3. Run `pytest` to verify grading works
4. Submit a PR

## Running Tests
```bash
pip install -e ".[dev]"
pytest -v
```

## Architecture

See `architecture.svg` in the repo root for the full system diagram.
