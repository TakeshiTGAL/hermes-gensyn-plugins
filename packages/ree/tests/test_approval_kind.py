"""denial_kind reads Hermes outcome, not the English message."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if os.environ.get("REE_APPROVAL_CHILD") == "1":
    ROOT = Path(__file__).resolve().parents[1]
    try:
        import tools.approval as approval
        import tools.approval_context as context
    except Exception as exc:
        print(json.dumps({"skip": str(exc)}))
        raise SystemExit(0)
    sys.path.insert(0, str(ROOT))
    import docker
    import gate
    from support import sample_file
    import importlib.util
    spec = importlib.util.spec_from_file_location("ree_plugin_tools", ROOT / "tools.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    approval._yolo_active = lambda: False
    context._is_cron_approval_context = lambda: False
    context._get_approval_mode = lambda: "manual"
    context._is_single_query_approval_context = lambda: False
    context._is_unattended_platform_approval_context = lambda: False
    for name in ("HERMES_INTERACTIVE", "HERMES_GATEWAY_SESSION", "HERMES_PLUGIN_HOST_PROCESS"):
        os.environ.pop(name, None)
    no_human = (
        "BLOCKED: Tool 'ree_infer' requires approval (reason) but no interactive "
        "user or gateway is present to approve it."
    )
    constructors = []
    denied = approval._denied("could not", pattern_key="k", description="d", outcome="denied")
    constructors.append(gate.denial_kind(denied) == "approval_denied")
    for outcome in ("timeout", "notify_failed", "cancelled", "blocked"):
        result = approval._denied("x", pattern_key="k", description="d", outcome=outcome)
        constructors.append(result["outcome"] == outcome and gate.denial_kind(result) == "approval_unavailable")
    blocked = approval._blocked(no_human, pattern_key="k", description="d")
    constructors.append("outcome" not in blocked and gate.denial_kind(blocked) == "approval_unavailable")
    constructors.append(gate.denial_kind(approval._approved()) == "approval_unavailable")
    seen = []
    real = approval.request_tool_approval

    def wrapped(tool_name, reason, rule_key="", approval_callback=None):
        result = real(tool_name, reason, rule_key=rule_key, approval_callback=approval_callback)
        seen.append({"outcome": result.get("outcome") if isinstance(result, dict) else None})
        return result

    approval.request_tool_approval = wrapped
    started = []

    def boom(argv, request, env, deadline, cwd=None):
        from process import ChildResult
        rest = argv[1:] if argv[:1] == ["docker"] else argv
        if rest[:1] == ["--context"] and len(rest) >= 2:
            rest = rest[2:]
        if rest[:1] == ["info"]:
            return ChildResult(0, b"12514787328\n", b"")
        if rest[:1] == ["context"]:
            return ChildResult(0, b"colima\n", b"")
        started.append([part for part in argv if part in ("validate", "verify", "run-all")])
        if "validate" in argv:
            if "--cidfile" in argv:
                Path(argv[argv.index("--cidfile") + 1]).write_text("ab" * 32)
            text = (
                "I gensyn_sdk.cli:   prompt_hash: PASS\n"
                "  tools_hash: PASS\n"
                "  parameters_hash: PASS\n"
                "  receipt_hash: PASS\n"
            )
            return ChildResult(0, text.encode(), b"")
        raise AssertionError(argv)

    docker.run_child = boom

    def container_names():
        try:
            proc = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True,
            )
        except FileNotFoundError:
            return None
        if proc.returncode != 0:
            return None
        return sorted(line for line in proc.stdout.splitlines() if line.startswith("gensyn-ree-"))

    before = container_names()
    infer = json.loads(plugin.ree_infer({
        "model": "Qwen/Qwen2.5-0.5B", "prompt": "Say yes.", "max_new_tokens": 4,
    }))
    with tempfile.TemporaryDirectory() as folder:
        path = sample_file(Path(folder))
        verify = json.loads(plugin.ree_verify_receipt({"receipt_path": str(path)}))
    after = container_names()
    print(json.dumps({
        "constructors": constructors,
        "started": started,
        "names_same": before == after,
        "seen": seen,
        "infer": infer.get("error_type"),
        "verify": verify.get("error_type"),
        "infer_retryable": infer.get("retryable"),
        "verify_retryable": verify.get("retryable"),
        "infer_message": infer.get("message"),
        "verify_message": verify.get("message"),
    }))
    raise SystemExit(0)

import pytest

import gate

_NO_HUMAN = (
    "BLOCKED: Tool 'ree_infer' requires approval (reason) but no interactive "
    "user or gateway is present to approve it."
)
# Return shapes of tools/approval.py: _denied, _blocked, _approved, smart deny.
SHAPES = (
    ("denied", {"approved": False, "outcome": "denied", "message": "could not", "user_consent": False}),
    ("timeout", {"approved": False, "outcome": "timeout", "message": "", "user_consent": False}),
    ("notify_failed", {"approved": False, "outcome": "notify_failed", "message": "", "user_consent": False}),
    ("cancelled", {"approved": False, "outcome": "cancelled", "message": "", "user_consent": False}),
    ("blocked", {"approved": False, "outcome": "blocked", "message": "", "user_consent": False}),
    ("blank-outcome", {"approved": False, "outcome": "", "message": ""}),
    ("null-outcome", {"approved": False, "outcome": None, "message": ""}),
    ("number-outcome", {"approved": False, "outcome": 1, "message": ""}),
    ("user-denied-text", {"approved": False, "message": "BLOCKED: User denied this command."}),
    ("no-human", {"approved": False, "message": _NO_HUMAN, "pattern_key": "k", "description": "d"}),
    ("smart", {"approved": False, "message": "BLOCKED by smart approval", "smart_denied": True}),
    ("approved", {"approved": True, "message": None}),
    ("none", None),
    ("blank", ""),
    ("text", "User denied"),
    ("zero", 0),
    ("list", []),
    ("empty", {}),
)


@pytest.mark.parametrize("label,result", SHAPES, ids=[item[0] for item in SHAPES])
def test_only_outcome_denied_is_a_user_refusal(label, result):
    kind = gate.denial_kind(result)
    if label == "denied":
        assert kind == "approval_denied"
    else:
        assert kind == "approval_unavailable"


def test_noninteractive_entries_do_not_start_a_container():
    env = os.environ.copy()
    env["REE_APPROVAL_CHILD"] = "1"
    for name in ("HERMES_INTERACTIVE", "HERMES_GATEWAY_SESSION", "HERMES_PLUGIN_HOST_PROCESS"):
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, __file__], env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    if report.get("skip"):
        pytest.skip(report["skip"])
    assert report["constructors"] == [True, True, True, True, True, True, True]
    assert report["started"] == [["validate"]]
    assert report["names_same"] is True
    assert report["infer"] == "approval_unavailable"
    assert report["verify"] == "approval_unavailable"
    assert report["infer_retryable"] is False
    assert report["verify_retryable"] is False
    assert len(report["seen"]) == 2
    for result in report["seen"]:
        assert result["outcome"] != "denied"
    for message in (report["infer_message"], report["verify_message"]):
        assert "said no" not in message
        assert "not obtained" in message
