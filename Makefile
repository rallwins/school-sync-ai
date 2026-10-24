# Not run on the Windows dev machine (no make installed); the commands are the same as in README.
test:
	cd backend && python -m pytest -q
lint:
	cd backend && python -m ruff check . && python -m mypy app
fixtures:
	python data/synthetic/generate_fixtures.py
