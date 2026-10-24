import os

# Tests must be hermetic: never read a developer's real backend/.env or SCHOOLSYNC_* variables
# (they can hold live Google credentials). This runs before any app module builds Settings.
for _k in [k for k in os.environ if k.startswith("SCHOOLSYNC_")]:
    del os.environ[_k]
from app.config import Settings

Settings.model_config["env_file"] = None

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYN = ROOT / "data" / "synthetic"


@pytest.fixture(scope="session")
def calendar_pdf() -> bytes:
    runpy.run_path(str(SYN / "generate_fixtures.py"), run_name="__main__")
    return (SYN / "maple_grove_2025_26.pdf").read_bytes()


@pytest.fixture(scope="session")
def truth() -> dict:
    return json.loads((SYN / "maple_grove_2025_26.truth.json").read_text())
