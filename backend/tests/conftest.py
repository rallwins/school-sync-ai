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
