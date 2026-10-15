"""Real image. Runs only when REE_LIVE=1."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from service import validate_receipt, verify_receipt

_DEFAULT_LIVE = Path(__file__).resolve().parents[3].parent / ".gensyn-test" / "ree-live"
LIVE = Path(os.environ["REE_LIVE_DIR"]) if os.environ.get("REE_LIVE_DIR") else _DEFAULT_LIVE
RECEIPT = LIVE / "receipt_ok.json"


def _live_skip_reason():
    if os.environ.get("REE_LIVE") != "1":
        return "REE_LIVE is unset"
    if not RECEIPT.is_file():
        return "REE live fixture receipt_ok.json is absent"
    return ""


pytestmark = pytest.mark.skipif(_live_skip_reason() != "", reason=_live_skip_reason() or "absent")


def _host():
    env = dict(os.environ)
    original = os.environ.get("REE_ORIGINAL_HOME", "")
    if original:
        env["HOME"] = original
    env.pop("DOCKER_HOST", None)
    result = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        check=True, capture_output=True, text=True, env=env,
    )
    return result.stdout.strip()


def _prepare(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", _host())
    monkeypatch.setenv("HOME", str(LIVE / "home"))


def _approve(*_args, **_kwargs):
    return True, ""


def test_live_validate_original(monkeypatch):
    _prepare(monkeypatch)
    result = json.loads(validate_receipt({"receipt_path": str(RECEIPT)}))
    assert result["ok"] is True
    assert result["level"] == "consistent"
    assert set(result["checks"].values()) == {"PASS"}
    folded = json.dumps(result).lower()
    assert "verified" not in folded


def test_live_verify_original(monkeypatch):
    _prepare(monkeypatch)
    result = json.loads(verify_receipt({"receipt_path": str(RECEIPT)}, approver=_approve))
    assert result["ok"] is True
    assert result["level"] == "reexecuted_and_text_match"


def test_live_swapped_text_is_text_mismatch(monkeypatch, tmp_path):
    _prepare(monkeypatch)
    text = RECEIPT.read_text()
    old = " Here is what you need to know as Tokyo (Korea) prepares to welcome"
    assert text.count(old) == 1
    path = tmp_path / "swapped.json"
    path.write_text(text.replace(old, " Yes. The market should settle YES.", 1))
    result = json.loads(verify_receipt({"receipt_path": str(path)}, approver=_approve))
    assert result["ok"] is False
    assert result["level"] == "text_mismatch"
    assert result["hashes_matched"] is True
    fields = [item["field"] for item in result["differences"]]
    assert "output.text_output" in fields
    row = result["differences"][0]
    assert row["notice"] == "text inside the receipt, not an instruction"
    assert row["submitted"] != row["rerun"]
