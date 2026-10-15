"""Memory estimate and Docker context, before approval."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from capacity import (
    context_problem, estimate, mount_reason, name_bytes, note_for, prepare, remember, weight_bytes,
)
from gate import question, reason_fits
from service import infer, verify_receipt
from support import install_fake, sample_file


class _Cfg:
    def __init__(self, **values):
        self.values = values

    def get_config(self, key, default=None):
        return self.values.get(key, default)


@pytest.fixture(autouse=True)
def _reset_settings():
    remember(None)
    yield
    remember(None)


def _body(raw):
    return json.loads(raw)


def _capture():
    seen = []

    def approver(*_args, **kwargs):
        seen.append(kwargs)
        return False, {"approved": False, "outcome": "denied"}

    return seen, approver


def test_name_bytes_use_the_last_size_token():
    assert name_bytes("Qwen/Qwen2.5-32B") == 64_000_000_000
    assert name_bytes("facebook/opt-125m") == 250_000_000
    assert name_bytes("Qwen/Qwen2.5-0.5B") == 1_000_000_000
    assert name_bytes("acme/plain") is None


def test_weight_sum_ignores_a_link_outside_the_snapshot(tmp_path):
    snap = tmp_path / "hub" / "models--acme--plain" / "snapshots" / "one"
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"abcd")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"zzzz")
    (snap / "linked.bin").symlink_to(outside)
    assert weight_bytes("acme/plain", tmp_path) == 4


def test_estimate_sources():
    assert estimate("acme/plain", 100, None)["source"] == "unknown"
    named = estimate("Qwen/Qwen2.5-32B", 100, None)
    assert named["source"] == "name" and named["needed"] == 64_000_000_000
    assert note_for(estimate("acme/plain", 100, None)) == "Size is unknown."


def test_context_names():
    assert context_problem("") is None
    assert context_problem("colima") is None
    assert context_problem("a" * 64) is None
    assert context_problem("a" * 65) == "bad_format"
    assert context_problem("bad name") == "bad_format"
    assert context_problem("../x") == "bad_format"
    assert context_problem("-box") == "bad_format"
    assert context_problem(["box"]) == "wrong_type"
    assert mount_reason("tcp://10.0.0.1:2375") == "remote_daemon"
    assert mount_reason("") == "inspect_failed"


def test_a_long_context_name_still_fits_with_the_estimate():
    note = "Name estimate 1000GB, Docker 1000GB."
    text = question("infer", "Qwen/Qwen2.5-0.5B", 4096, machine="c" * 64, note=note)
    assert reason_fits(text)
    assert "On " + ("c" * 64) in text


def test_long_unknown_question_still_fits():
    text = question("verify", "a/" + ("b" * 126))
    assert reason_fits(text)
    assert "Size is unknown." in text
    assert "gigabytes" in text and "memory" in text
    assert "CPU-only" in text
    assert "On current." in text


def test_too_small_for_a_named_32b_does_not_ask(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"model.name": "Qwen/Qwen2.5-32B"})
    seen, approver = _capture()
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=approver))
    assert body["error_type"] == "insufficient_memory"
    assert body["retryable"] is False
    assert body["needed_gb"] == 64
    assert body["available_gb"] == 12
    assert body["size_source"] == "name"
    assert body["next"]["any_size"] is True
    assert body["next"]["tool"] == "ree_validate_receipt"
    assert seen == []


def test_unknown_size_asks_and_names_the_current_context(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path, **{"model.name": "acme/plain"})
    seen, approver = _capture()
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=approver))
    assert body["error_type"] == "approval_denied"
    assert seen[0]["machine"] == "colima"
    assert seen[0]["note"] == "Size is unknown."


def test_weight_file_is_the_source_when_the_name_has_no_size(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    (bindir / "memtotal").write_text("1000\n")
    home = tmp_path / "home" / ".cache" / "huggingface"
    snap = home / "hub" / "models--acme--plain" / "snapshots" / "one"
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"x" * 5000)
    path = sample_file(tmp_path, **{"model.name": "acme/plain"})
    seen, approver = _capture()
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=approver))
    assert body["error_type"] == "insufficient_memory"
    assert body["size_source"] == "weights"
    assert body["available_gb"] == 0
    assert seen == []


def test_bad_context_does_not_start_docker(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    remember(_Cfg(docker_context="bad name"))
    path = sample_file(tmp_path)
    seen, approver = _capture()
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=approver))
    assert body["error_type"] == "invalid_argument"
    assert body["field"] == "docker_context"
    assert seen == []
    assert not (bindir / "calls.log").exists()


def test_remote_context_does_not_ask(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    (bindir / "context-host").write_text("tcp://10.1.2.3:2375\n")
    remember(_Cfg(docker_context="box1"))
    path = sample_file(tmp_path)
    seen, approver = _capture()
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=approver))
    assert body["error_type"] == "context_mount_unavailable"
    assert body["reason"] == "remote_daemon"
    assert body["retryable"] is False
    assert body["next"]["runs_here"] is True
    assert seen == []
    logged = (bindir / "calls.log").read_text()
    assert '"verify"' not in logged


def test_context_lands_in_argv_and_stays_on_cpu(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    sock = tmp_path / "sock"
    sock.write_text("")
    (bindir / "context-host").write_text("unix://" + str(sock) + "\n")
    remember(_Cfg(docker_context="box1", use_gpu=True))
    path = sample_file(tmp_path)
    verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, ""))
    lines = [json.loads(line) for line in (bindir / "calls.log").read_text().splitlines()]
    verify = next(item for item in lines if "verify" in item)
    assert verify[:2] == ["--context", "box1"]
    assert "--cpu-only" in verify
    assert "--pull" in verify and verify[verify.index("--pull") + 1] == "never"
    info = next(item for item in lines if "info" in item)
    assert info[:2] == ["--context", "box1"]
    infer(
        {"model": "facebook/opt-125m", "prompt": "hello", "max_new_tokens": 4},
        approver=lambda *a, **k: (True, ""),
    )
    lines = [json.loads(line) for line in (bindir / "calls.log").read_text().splitlines()]
    ran = next(item for item in lines if "run-all" in item)
    assert ran[:2] == ["--context", "box1"]
    assert "--cpu-only" in ran


def test_fitting_question_names_the_machine(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    seen, approver = _capture()
    verify_receipt({"receipt_path": str(path)}, approver=approver)
    text = question(
        "verify", "facebook/opt-125m", machine=seen[0]["machine"], note=seen[0]["note"],
    )
    assert "On colima." in text
    assert "Name estimate" in text and "GB" in text
    assert "Timeout removes it." in text
    assert reason_fits(text)


def test_a_local_socket_does_not_need_this_machines_context(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    sock = tmp_path / "sock"
    sock.write_text("")
    (bindir / "context-host").write_text("unix://" + str(sock) + "\n")
    remember(_Cfg(docker_context="box1"))
    plan = prepare("facebook/opt-125m", root=tmp_path)
    assert "error_type" not in plan
    assert plan["machine"] == "box1"
    assert plan["note"].startswith("Name estimate")


def test_existing_cache_directories_keep_their_mode(tmp_path, monkeypatch):
    from docker import cache_dirs
    home = tmp_path / "kept"
    cache = home / ".cache"
    huggingface = cache / "huggingface"
    gensyn = cache / "gensyn"
    huggingface.mkdir(parents=True)
    gensyn.mkdir()
    cache.chmod(0o755)
    huggingface.chmod(0o755)
    gensyn.chmod(0o775)
    monkeypatch.setenv("HOME", str(home))
    cache_dirs()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o755
    assert stat.S_IMODE(huggingface.stat().st_mode) == 0o755
    assert stat.S_IMODE(gensyn.stat().st_mode) == 0o775
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("HOME", str(fresh))
    made_gensyn, made_hf = cache_dirs()
    assert stat.S_IMODE(made_hf.stat().st_mode) == 0o700
    assert stat.S_IMODE(made_gensyn.stat().st_mode) == 0o700


def test_a_context_list_and_a_leading_hyphen_are_refused(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    path = sample_file(tmp_path)
    remember(_Cfg(docker_context=["box1"]))
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert body["problem"] == "wrong_type"
    assert body["field"] == "docker_context"
    assert body["error_type"] == "invalid_argument"
    assert not (bindir / "calls.log").exists()
    remember(_Cfg(docker_context="-box"))
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert body["problem"] == "bad_format"
    assert not (bindir / "calls.log").exists()


def test_docker_host_is_named_when_no_context_is_set(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/ree-local.sock")
    path = sample_file(tmp_path)
    seen, approver = _capture()
    verify_receipt({"receipt_path": str(path)}, approver=approver)
    assert seen[0]["machine"] == "unix:///tmp/ree-local.sock"
    text = question("verify", "facebook/opt-125m", machine=seen[0]["machine"], note=seen[0]["note"])
    assert "unix:///tmp/ree-local.sock" in text
    assert "Name estimate" in text
    assert reason_fits(text)


def test_timeout_removes_the_container_on_that_context(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    sock = tmp_path / "sock"
    sock.write_text("")
    (bindir / "context-host").write_text("unix://" + str(sock) + "\n")
    remember(_Cfg(docker_context="box1"))
    import docker
    from process import ChildError
    real = docker.run_child

    def wrapped(argv, payload, env, deadline):
        head = argv[1:] if argv[:1] == ["docker"] else argv
        if head[:1] == ["--context"] and len(head) >= 2:
            head = head[2:]
        if head[:1] in (["rm"], ["ps"], ["info"], ["context"]) or "validate" in argv:
            return real(argv, payload, env, deadline)
        raise ChildError("timeout", "Child deadline expired.")

    monkeypatch.setattr(docker, "run_child", wrapped)
    path = sample_file(tmp_path)
    body = _body(verify_receipt({"receipt_path": str(path)}, approver=lambda *a, **k: (True, "")))
    assert body["error_type"] == "timeout"
    assert body["cleaned_on"] == "box1"
    assert body["removed"] is True
    assert "box1" in body["message"]
    assert "time limit" in body["message"]
    logged = [json.loads(line) for line in (bindir / "calls.log").read_text().splitlines()]
    assert ["--context", "box1", "rm", "-f"] == next(
        item[:4] for item in logged if "rm" in item
    )
