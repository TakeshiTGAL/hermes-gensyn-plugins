from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("REE_ORIGINAL_HOME", os.environ.get("HOME", ""))
    home = tmp_path / "pytest-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("DOCKER_HOST", raising=False)
