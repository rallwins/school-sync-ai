# Contributing

1. `cd backend && python -m pip install -r requirements-dev.txt`
2. Before a PR: `pytest -q`, `ruff check .`, `mypy app` must pass.
3. Test data must be synthetic. Add new fixtures via `data/synthetic/generate_fixtures.py` with ground truth.
4. Do not claim a feature works unless a test or a recorded manual run shows it.
