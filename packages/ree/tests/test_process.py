from __future__ import annotations

import os
import time

import pytest

from collections import namedtuple

from docker import DockerError, run_named
from doctor import run_doctor
from process import ChildError, run_child
from support import install_fake
from docker import child_env


def test_secret_environment_is_not_forwarded(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_TOKEN", "marker-token")
    monkeypatch.setenv("SYNTHETIC_PARENT_SECRET", "marker-secret")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("PYTHONPATH", "should-not-pass")
    result = run_child(["docker", "env"], b"", child_env(), 2)
    text = result.stdout.decode()
    assert "HF_TOKEN" not in text
    assert "marker-token" not in text
    assert "SYNTHETIC_PARENT_SECRET" not in text
    assert "PYTHONPATH" not in text
    assert "should-not-pass" not in text
    assert "LANG" in text


def test_deadline_kills_the_named_container(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    started = time.monotonic()
    with pytest.raises(DockerError) as caught:
        run_named(["docker", "sleep"], 0.3, "gensyn-ree-dead")
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 2
    log = (bindir / "calls.log").read_text()
    assert "rm" in log
    assert "ps" in log
    assert "gensyn-ree-dead" in log


def test_output_cap(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    with pytest.raises(DockerError) as caught:
        run_named(["docker", "huge"], 2, "gensyn-ree-huge")
    assert caught.value.kind == "invalid_response"
    log = (bindir / "calls.log").read_text()
    assert "rm" in log
    assert "gensyn-ree-huge" in log
    assert "still running" not in str(caught.value)


def test_direct_child_deadline(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    started = time.monotonic()
    with pytest.raises(ChildError) as caught:
        run_child(["docker", "sleep"], b"", child_env(), 0.25)
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 2


def test_doctor_reports_image_and_daemon(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    healthy = run_doctor(runner=run_child)
    assert healthy["docker"]["status"] == "ok"
    assert healthy["daemon"]["status"] == "ok"
    assert healthy["image"]["status"] == "ok"
    assert healthy["overall"] == "healthy"
    (bindir / "missing-image").write_text("1")
    missing = run_doctor(runner=run_child)
    assert missing["image"]["status"] == "error"
    assert "REE-Binary-License" in missing["image"]["message"]
    assert "docker pull" in missing["image"]["message"]
    (bindir / "daemon-down").write_text("1")
    down = run_doctor(runner=run_child)
    assert down["daemon"]["status"] == "error"
    assert "REE-Binary-License" not in down["image"]["message"]
    assert "not checked" in down["image"]["message"]
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    os.makedirs(tmp_path / "empty", exist_ok=True)
    absent = run_doctor(runner=run_child)
    assert absent["docker"]["status"] == "error"
    assert absent["overall"] == "error"
    from doctor import doctor_main
    assert doctor_main() == 1


def test_interrupt_removes_the_named_container(tmp_path, monkeypatch):
    bindir = install_fake(tmp_path, monkeypatch)
    import docker
    real = docker.run_child

    def wrapped(argv, payload, env, deadline):
        if argv[1:2] == ["rm"] or argv[:1] == ["ps"] or "ps" in argv:
            return real(argv, payload, env, deadline)
        raise KeyboardInterrupt

    monkeypatch.setattr(docker, "run_child", wrapped)
    with pytest.raises(KeyboardInterrupt):
        run_named(["docker", "run", "--name", "gensyn-ree-stop"], 5, "gensyn-ree-stop")
    log = (bindir / "calls.log").read_text()
    assert "rm" in log
    assert "gensyn-ree-stop" in log


def test_doctor_names_a_leftover_container(tmp_path, monkeypatch):
    from capacity import remember
    remember(None)
    bindir = install_fake(tmp_path, monkeypatch)
    (bindir / "leftover").write_text("gensyn-ree-old\texited\nnot-ours\trunning\n")
    report = run_doctor()
    assert report["leftovers"]["names"] == ["gensyn-ree-old"]
    assert report["leftovers"]["states"] == ["exited"]
    assert "still running" not in report["leftovers"]["message"]
    assert report["overall"] == "warn"
    (bindir / "leftover").write_text("gensyn-ree-live\trunning\n")
    running = run_doctor()
    assert running["leftovers"]["names"] == ["gensyn-ree-live"]
    assert "still running" in running["leftovers"]["message"]
    from capacity import remember
    class _Cfg:
        def get_config(self, key, default=None):
            return "box1" if key == "docker_context" else default
    remember(_Cfg())
    named = run_doctor()
    assert "box1" in named["leftovers"]["message"]
    logged = (bindir / "calls.log").read_text()
    assert '"--context"' in logged and '"box1"' in logged
    remember(None)


def test_low_disk_is_not_a_success_exit(tmp_path, monkeypatch):
    install_fake(tmp_path, monkeypatch)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr("doctor.shutil.disk_usage", lambda path: usage(10, 9, 1))
    report = run_doctor()
    assert report["overall"] == "warn"
    from doctor import doctor_main
    assert doctor_main() == 1
