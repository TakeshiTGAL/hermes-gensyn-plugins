from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from bridge import ENV_ALLOWLIST, _environment
from process import ChildError, run_child
from rate import RateLimiter


def script(tmp_path, text):
    path = tmp_path / "fake_node.py"
    path.write_text(text)
    return str(path)


def test_child_round_trip_and_minimal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_PARENT_SECRET", "must-not-leak")
    path = script(
        tmp_path,
        "import json,os,sys\n"
        "body=sys.stdin.buffer.read()\n"
        "print(json.dumps({'body':body.decode(),'secret':"
        "'SYNTHETIC_PARENT_SECRET' in os.environ}))\n",
    )
    result = run_child(
        [sys.executable, path],
        b'{"hello":"world"}',
        {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path)},
        2.0,
    )
    assert result.returncode == 0
    assert b'"secret": false' in result.stdout
    assert b"hello" in result.stdout


def test_bridge_environment_passes_key_only_to_keyed_reads(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "marker-key")
    monkeypatch.setenv("SYNTHETIC_PRIVATE_KEY", "must-not-leak")
    keyless = _environment(False)
    keyed = _environment(True)
    assert "DELPHI_API_ACCESS_KEY" not in keyless
    assert keyed["DELPHI_API_ACCESS_KEY"] == "marker-key"
    assert "SYNTHETIC_PRIVATE_KEY" not in keyed
    allowed = {*ENV_ALLOWLIST, "NODE_OPTIONS"}
    assert set(keyless) <= allowed
    assert set(keyed) <= allowed | {"DELPHI_API_ACCESS_KEY"}


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_child_output_cap(tmp_path, stream):
    target = "sys.stdout" if stream == "stdout" else "sys.stderr"
    path = script(tmp_path, f"import sys\n{target}.write('x'*300000)\n")
    with pytest.raises(ChildError) as caught:
        run_child([sys.executable, path], b"", {}, 2.0)
    assert caught.value.kind == "invalid_response"


def test_child_stdin_cap(tmp_path):
    path = script(tmp_path, "import sys\nsys.stdin.buffer.read()\n")
    with pytest.raises(ChildError) as caught:
        run_child([sys.executable, path], b"x" * 70000, {}, 2.0)
    assert caught.value.kind == "invalid_argument"


def test_child_deadline_kills_process_group(tmp_path):
    path = script(tmp_path, "import time\ntime.sleep(10)\n")
    started = time.monotonic()
    with pytest.raises(ChildError) as caught:
        run_child([sys.executable, path], b"", {}, 0.25)
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 1.0


def test_grandchild_holding_pipe_cannot_extend_deadline(tmp_path):
    path = script(
        tmp_path,
        "import subprocess,sys\n"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])\n",
    )
    started = time.monotonic()
    with pytest.raises(ChildError) as caught:
        run_child([sys.executable, path], b"", {}, 0.25)
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 1.0


def test_rate_limiter_allows_at_most_thirty_concurrent_reservations():
    limiter = RateLimiter(limit=30, window=60.0)
    barrier = threading.Barrier(51)
    decisions = []

    def reserve():
        barrier.wait()
        decisions.append(limiter.reserve(1))

    threads = [threading.Thread(target=reserve) for _ in range(50)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert decisions.count(True) == 30
    assert decisions.count(False) == 20


def test_zero_reservation_does_not_consume_the_window():
    limiter = RateLimiter(limit=1, window=60.0)
    assert limiter.reserve(0) is True
    assert limiter.reserve(1) is True
    assert limiter.reserve(0) is True
    assert limiter.reserve(1) is False


def test_bridge_child_starts_in_an_empty_directory(monkeypatch):
    seen = {}

    def fake(_argv, _request, _env, _deadline, cwd=None):
        seen["cwd"] = cwd
        seen["names"] = os.listdir(cwd)
        return type("Child", (), {"returncode": 0, "stdout": b'{"ok":true}\n'})()

    import bridge

    monkeypatch.setattr(bridge, "run_child", fake)
    bridge.call_bridge("list_markets", {}, needs_key=False, budget=1, network="testnet")
    assert seen["cwd"] != os.getcwd()
    assert seen["names"] == []
    assert not os.path.exists(seen["cwd"])


def _outside_quotes(line):
    out = []
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\" and quote != "'":
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def test_product_lines_hold_one_statement():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*"):
        if path.suffix != ".py" or "tests" in path.parts or "node_modules" in path.parts:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            assert ";" not in _outside_quotes(line), f"{path.name}:{number}"


def test_failed_request_reservation_is_not_returned():
    limiter = RateLimiter(limit=3, window=60.0)
    assert limiter.reserve(3)
    assert not limiter.reserve(1)
