from __future__ import annotations

import os
import time

import pytest

from service import infer, read_capped, validate_receipt, verify_receipt
from service import _DROP, _echo
from support import install_fake, sample_file


def _body(text):
    import json
    return json.loads(text)


@pytest.mark.parametrize("tool", ("validate", "verify", "infer"))
@pytest.mark.parametrize("prompt,needle,kind", (
    ("SCENARIO daemon", "not reachable", "docker_unavailable"),
    ("SCENARIO cannot-connect", "not reachable", "docker_unavailable"),
    ("SCENARIO denied", "not reachable", "docker_unavailable"),
    ("SCENARIO no-image", "REE-Binary-License", "image_missing"),
    ("SCENARIO conflict", "did not start", "container_not_started"),
    ("SCENARIO other-image", "did not start", "container_not_started"),
))
def test_each_tool_reports_infra_without_a_level(tmp_path, monkeypatch, tool, prompt, needle, kind):
    install_fake(tmp_path, monkeypatch)
    approver = lambda *args, **kwargs: (True, "")
    if tool == "infer":
        raw = infer(
            {"model": "facebook/opt-125m", "prompt": prompt, "max_new_tokens": 4},
            approver=approver,
        )
    else:
        path = sample_file(tmp_path, **{"input.prompt": prompt})
        call = validate_receipt if tool == "validate" else verify_receipt
        raw = call({"receipt_path": str(path)}, approver=approver) if tool == "verify" else call({"receipt_path": str(path)})
    result = _body(raw)
    assert result["ok"] is False
    assert result["error_type"] == kind
    assert needle in result["message"]
    assert "level" not in result
    if kind != "config":
        lowered = result["message"].lower()
        assert "receipt" not in lowered
        assert "verify" not in lowered
        assert "hash" not in lowered
    if needle != "REE-Binary-License":
        assert "REE-Binary-License" not in result["message"]


@pytest.mark.parametrize("char", sorted(_DROP))
def test_direction_controls_are_removed(char):
    text, _cut = _echo("ok" + char + "go")
    assert char not in text
    assert text == "okgo"


READABLE = (
    ("model.name", "Qwen/Qwen2.5-0.5B"),
    ("output.text_output", "swapped"),
    ("output.finish_reason", "eos_token"),
    ("output.token_count", 3),
    ("input.prompt", "a different prompt"),
)


@pytest.mark.parametrize("path,value", READABLE)
def test_each_readable_field_is_text_mismatch(tmp_path, monkeypatch, path, value):
    install_fake(tmp_path, monkeypatch)
    receipt = sample_file(tmp_path, **{path: value})
    result = _body(verify_receipt(
        {"receipt_path": str(receipt)}, approver=lambda *args, **kwargs: (True, ""),
    ))
    assert result["level"] == "text_mismatch"
    fields = [item["field"] for item in result["differences"]]
    assert path in fields


def test_commit_hash_difference_is_a_reexecution_mismatch(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    receipt = sample_file(tmp_path, **{"model.commit_hash": "0" * 40})
    result = _body(verify_receipt(
        {"receipt_path": str(receipt)}, approver=lambda *args, **kwargs: (True, ""),
    ))
    assert result["level"] == "reexecution_mismatch"
    assert result["hashes_matched"] is False
    fields = [item["field"] for item in result["differences"]]
    assert "model.commit_hash" in fields


def test_device_fifo_and_symlink_are_not_read(tmp_path):
    started = time.monotonic()
    device = _body(validate_receipt({"receipt_path": "/dev/zero"}))
    assert time.monotonic() - started < 1
    assert device["ok"] is False
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe)
    assert _body(validate_receipt({"receipt_path": str(pipe)}))["ok"] is False
    link = tmp_path / "link"
    link.symlink_to("/dev/zero")
    assert _body(validate_receipt({"receipt_path": str(link)}))["ok"] is False


def test_newline_prompt_fails_before_approval(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    seen = []
    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "hello\nworld", "max_new_tokens": 4},
        approver=lambda *args, **kwargs: seen.append(args) or (True, ""),
    ))
    assert result["ok"] is False
    assert result["problem"] == "bad_format"
    assert "newline" in result["expected"]
    assert "hello" not in result["expected"]
    assert seen == []
    assert not (bindir / "calls.log").exists()


def test_cache_file_is_a_structured_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".cache").write_text("not-a-directory")
    monkeypatch.setenv("HOME", str(home))
    path = sample_file(tmp_path)
    result = _body(validate_receipt({"receipt_path": str(path)}))
    assert result["ok"] is False
    assert result["error_type"] == "config"


def test_hash_line_on_a_passing_verify_still_compares_text(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO hashline"})
    result = _body(verify_receipt(
        {"receipt_path": str(path)}, approver=lambda *args, **kwargs: (True, ""),
    ))
    assert result["ok"] is True
    assert result["level"] == "reexecuted_and_text_match"


def test_infer_keeps_a_receipt_when_the_log_names_an_image(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    result = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "SCENARIO poison-infer", "max_new_tokens": 4},
        approver=lambda *args, **kwargs: (True, ""),
    ))
    assert result["ok"] is True
    assert result["level"] == "inferred"
    assert "REE-Binary-License" not in result.get("message", "")


def test_another_images_absence_is_not_our_pull_consent(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"input.prompt": "SCENARIO other-image"})
    verified = _body(verify_receipt(
        {"receipt_path": str(path)}, approver=lambda *args, **kwargs: (True, ""),
    ))
    inferred = _body(infer(
        {"model": "facebook/opt-125m", "prompt": "SCENARIO other-image", "max_new_tokens": 4},
        approver=lambda *args, **kwargs: (True, ""),
    ))
    assert verified["error_type"] == "container_not_started"
    assert inferred["error_type"] == "container_not_started"
    assert "level" not in verified
    assert "level" not in inferred
    assert "REE-Binary-License" not in verified["message"]
    assert "REE-Binary-License" not in inferred["message"]


def test_read_capped_stops_at_the_size(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (1_048_577))
    payload, problem = read_capped(big)
    assert payload is None
    assert "1 MiB" in problem
    small = tmp_path / "small.bin"
    small.write_bytes(b"{}")
    payload, problem = read_capped(small)
    assert problem is None
    assert payload == b"{}"
