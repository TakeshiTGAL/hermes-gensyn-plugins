from __future__ import annotations

import json

import pytest

from docker import DockerError, infer_argv, validate_argv, verify_argv
from service import validate_receipt, verify_receipt
from support import install_fake, sample_file


def test_validate_argv_is_network_none_and_one_file(tmp_path):
    argv = validate_argv("gensyn-ree-abc", tmp_path / "receipt.json", tmp_path / "cid")
    assert argv[argv.index("--network") + 1] == "none"
    assert "--cpu-only" not in argv
    assert "--privileged" not in argv
    assert "--gpus" not in argv
    assert "host" not in argv
    assert argv[argv.index("--pull") + 1] == "never"
    assert "--cidfile" in argv
    assert any(item.endswith(":/mnt/receipt/receipt.json:ro") for item in argv)
    assert "sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec" in " ".join(argv)


def test_verify_and_infer_do_not_take_user_text_as_options(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    verify = verify_argv("gensyn-ree-abc", tmp_path / "receipt.json", tmp_path / "tasks", tmp_path / "cid")
    assert "--network" not in verify
    assert "--cpu-only" in verify
    assert "--privileged" not in verify
    infer = infer_argv(
        "gensyn-ree-abc", tmp_path / "tasks", "facebook/opt-125m", "hello --network none", 4,
        tmp_path / "cid",
    )
    assert infer[infer.index("--prompt-text") + 1] == "hello --network none"
    assert infer.count("--network") == 0
    assert "--gpus" not in infer


def test_dash_prompt_is_rejected_before_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(DockerError):
        infer_argv("gensyn-ree-abc", tmp_path / "tasks", "facebook/opt-125m", "--cpu-only", 4, tmp_path / "cid")


def test_recorded_validate_argv_matches_the_builder(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    validate_receipt({"receipt_path": str(path)})
    recorded = json.loads((bindir / "calls.log").read_text().splitlines()[0])
    assert recorded[recorded.index("--network") + 1] == "none"
    assert "--cpu-only" not in recorded
    verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, ""))
    lines = (bindir / "calls.log").read_text().splitlines()
    second = json.loads(next(line for line in lines if '"verify"' in line))
    assert "--cpu-only" in second
    assert "--network" not in second
    assert any(item.endswith(":/home/gensyn/.cache/gensyn") for item in second)
    assert any(item.endswith(":/home/gensyn/.cache/huggingface") for item in second)
    assert not any("/.cache:" in item or item.endswith(":/home/gensyn/.cache") for item in second)
