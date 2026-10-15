"""Real discover_plugins path for closed approval contexts."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

if os.environ.get("REE_ENTRY_CHILD") == "1":
    scenario = sys.argv[1]
    root = Path(sys.argv[2])
    scratch = Path(tempfile.mkdtemp(prefix="ree-entry-"))
    home = scratch / "hh"
    user = scratch / "user"
    bindir = scratch / "bin"
    user.mkdir()
    bindir.mkdir()
    shutil.copytree(
        root, home / "plugins" / "hermes-gensyn-ree",
        ignore=shutil.ignore_patterns("tests", "__pycache__"),
    )
    approvals = {}
    extra = {}
    if scenario == "cron":
        extra["HERMES_CRON_SESSION"] = "1"
    elif scenario == "yolo":
        extra["HERMES_YOLO_MODE"] = "1"
        extra["HERMES_INTERACTIVE"] = "1"
    elif scenario == "off":
        extra["HERMES_INTERACTIVE"] = "1"
        approvals["mode"] = False
    elif scenario == "unattended":
        extra["HERMES_SESSION_PLATFORM"] = "api_server"
    import yaml
    plugins = {"enabled": ["hermes-gensyn-ree"]}
    if scenario == "fit":
        plugins["entries"] = {
            "hermes-gensyn-ree": {"settings": {"docker_context": "box1", "use_gpu": False}},
        }
        extra["HERMES_INTERACTIVE"] = "1"
        (bindir / "sock").write_text("")
        (bindir / "sockpath").write_text(str(bindir / "sock"))
    (home / "config.yaml").write_text(yaml.safe_dump({
        "plugins": plugins,
        "approvals": approvals,
    }))
    docker_lines = [
        "#!" + sys.executable,
        "import json, sys",
        "from pathlib import Path",
        "log = Path(sys.argv[0]).resolve().parent / 'calls.log'",
        "with log.open('a') as handle:",
        "    handle.write(json.dumps(sys.argv[1:]) + chr(10))",
        "argv = sys.argv[1:]",
        "if argv[:1] == ['version']:",
        "    print('29.5.2')",
        "    raise SystemExit(0)",
        "if argv[:2] == ['image', 'inspect']:",
        "    print('sha256:ad683947a8c3a0fcb2567280268c0b01f17652a38c3f76838a398bd79aaff0ec')",
        "    raise SystemExit(0)",
        "rest = argv[2:] if argv[:1] == ['--context'] and len(argv) >= 3 else argv",
        "if rest[:1] == ['info']:",
        "    print('12514787328')",
        "    raise SystemExit(0)",
        "if rest[:2] == ['context', 'show']:",
        "    print('colima')",
        "    raise SystemExit(0)",
        "if rest[:2] == ['context', 'inspect']:",
        "    host = Path(sys.argv[0]).resolve().parent / 'sockpath'",
        "    print('unix://' + host.read_text().strip())",
        "    raise SystemExit(0)",
        "if argv[:1] == ['run'] and 'validate' in argv:",
        "    if '--cidfile' in argv:",
        "        Path(argv[argv.index('--cidfile') + 1]).write_text('ab' * 32)",
        "    sys.stdout.write('I gensyn_sdk.cli:   prompt_hash: PASS' + chr(10))",
        "    sys.stdout.write('  tools_hash: PASS' + chr(10))",
        "    sys.stdout.write('  parameters_hash: PASS' + chr(10))",
        "    sys.stdout.write('  receipt_hash: PASS' + chr(10))",
        "    raise SystemExit(0)",
        "raise SystemExit(125)",
        "",
    ]
    fake = bindir / "docker"
    fake.write_text("\n".join(docker_lines))
    fake.chmod(stat.S_IRWXU)
    for key in list(os.environ):
        if key.startswith("HERMES_"):
            del os.environ[key]
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HOME"] = str(user)
    os.environ["PATH"] = str(bindir) + ":/usr/bin:/bin"
    os.environ.pop("DOCKER_HOST", None)
    os.environ.update(extra)
    sys.path.insert(0, str(root))
    from support import sample_file
    receipt = sample_file(scratch)
    sys.path.remove(str(root))
    for name in (
        "tools", "support", "contract", "service", "docker", "gate", "jsonio",
        "official", "process", "schemas", "doctor",
    ):
        sys.modules.pop(name, None)
    from hermes_cli.plugins import discover_plugins
    discover_plugins()
    from tools.registry import registry
    asked = []
    if scenario == "fit":
        import types
        approval = types.ModuleType("tools.approval")
        context = types.ModuleType("tools.approval_context")

        def request(_name, text, rule_key=""):
            asked.append(text)
            return {"approved": False, "outcome": "denied"}

        approval.request_tool_approval = request
        approval._yolo_active = lambda: False
        context._is_cron_approval_context = lambda: False
        context._get_approval_mode = lambda: "manual"
        context._is_single_query_approval_context = lambda: False
        context._is_unattended_platform_approval_context = lambda: False
        sys.modules["tools.approval"] = approval
        sys.modules["tools.approval_context"] = context

    def call(name, args):
        raw = registry.dispatch(name, args)
        if isinstance(raw, str) and "Unknown tool" in raw:
            return {"skip": raw}
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return {"raw": str(raw)[:200]}

    infer = call("ree_infer", {
        "model": "facebook/opt-125m", "prompt": "Say yes.", "max_new_tokens": 4,
    })
    if infer.get("skip"):
        print(json.dumps({"skip": infer["skip"]}))
        raise SystemExit(0)
    verify = call("ree_verify_receipt", {"receipt_path": str(receipt)})
    lines = (bindir / "calls.log").read_text().splitlines() if (bindir / "calls.log").exists() else []
    runs = [json.loads(line) for line in lines if json.loads(line)[:1] == ["run"]]
    huge = {}
    if scenario == "fit":
        data = json.loads(receipt.read_text())
        data["model"]["name"] = "Qwen/Qwen2.5-32B"
        receipt.write_text(json.dumps(data))
        huge = call("ree_verify_receipt", {"receipt_path": str(receipt)})
        lines = (bindir / "calls.log").read_text().splitlines()
        runs = [json.loads(line) for line in lines if json.loads(line)[:1] == ["run"] or (
            json.loads(line)[:1] == ["--context"] and "run" in json.loads(line)
        )]
    print(json.dumps({
        "infer": infer.get("error_type"),
        "verify": verify.get("error_type"),
        "infer_runs": sum("run-all" in item for item in runs),
        "verify_runs": sum("verify" in item for item in runs),
        "validate_runs": sum("validate" in item for item in runs),
        "infer_message": (infer.get("message") or "")[:120],
        "verify_message": (verify.get("message") or "")[:120],
        "asked": asked,
        "huge": huge.get("error_type"),
        "needed_gb": huge.get("needed_gb"),
        "available_gb": huge.get("available_gb"),
        "size_source": huge.get("size_source"),
        "any_size": (huge.get("next") or {}).get("any_size"),
        "retryable": huge.get("retryable"),
    }))
    raise SystemExit(0)

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("cron", "yolo", "off", "unattended", "nohuman")


def test_closed_contexts_do_not_reexecute():
    pytest.importorskip("hermes_cli.plugins")
    pytest.importorskip("yaml")
    for name in SCENARIOS:
        proc = subprocess.run(
            [sys.executable, __file__, name, str(ROOT)],
            capture_output=True,
            text=True,
            env={**os.environ, "REE_ENTRY_CHILD": "1"},
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        report = json.loads(proc.stdout)
        if report.get("skip"):
            pytest.skip(report["skip"])
        assert report["infer"] == "approval_unavailable", report
        assert report["infer_runs"] == 0, report
        assert report["verify"] == "approval_unavailable", report
        assert report["verify_runs"] == 0, report
        assert report["validate_runs"] == 1, report


def test_entry_names_the_context_and_stops_a_large_model():
    pytest.importorskip("hermes_cli.plugins")
    pytest.importorskip("yaml")
    proc = subprocess.run(
        [sys.executable, __file__, "fit", str(ROOT)],
        capture_output=True, text=True, env={**os.environ, "REE_ENTRY_CHILD": "1"},
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    if report.get("skip"):
        pytest.skip(report["skip"])
    assert report["infer_runs"] == 0, report
    assert report["verify_runs"] == 0, report
    assert report["huge"] == "insufficient_memory", report
    assert report["needed_gb"] == 64 and report["available_gb"] == 12
    assert report["size_source"] == "name"
    assert report["any_size"] is True
    assert report["retryable"] is False
    assert report["asked"]
    assert all("box1" in text for text in report["asked"])
    assert any("GB" in text or "Size is unknown." in text for text in report["asked"])
