"""The public pre_tool_call mouth asks a person, then still refuses an unattended turn after always."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

if os.environ.get("REE_PUBLIC_CHILD") == "1":
    root = Path(sys.argv[1])
    scratch = Path(tempfile.mkdtemp(prefix="ree-public-"))
    home = scratch / "hh"
    user = scratch / "user"
    bindir = scratch / "bin"
    user.mkdir()
    bindir.mkdir()
    home.mkdir()
    for key in list(os.environ):
        if key.startswith("HERMES_"):
            del os.environ[key]
    os.environ["HOME"] = str(user)
    os.environ["HERMES_HOME"] = str(home)
    os.environ["HERMES_INTERACTIVE"] = "1"
    os.environ["PATH"] = str(bindir) + ":/usr/bin:/bin"
    os.environ.pop("DOCKER_HOST", None)
    # This home only. Hermes's default load deadline is 10s; a busy machine
    # abandons register() and the tools never appear. 0 waits until load finishes.
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - hermes-gensyn-ree\n  load_timeout_seconds: 0\n"
    )
    shutil.copytree(
        root, home / "plugins" / "hermes-gensyn-ree",
        ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
    )
    sys.path.insert(0, str(root / "tests"))
    sys.path.insert(0, str(root))
    from support import FAKE, sample_file
    receipt = sample_file(scratch)
    fake = bindir / "docker"
    fake.write_text(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
    fake.chmod(stat.S_IRWXU)
    (bindir / "template.json").write_text(receipt.read_text())
    for name in (
        "tools", "support", "contract", "service", "docker", "gate", "jsonio",
        "official", "process", "schemas", "doctor", "capacity",
    ):
        sys.modules.pop(name, None)
    sys.path.remove(str(root))

    from hermes_cli.plugins import (
        _dispatch_pre_tool_call_hooks,
        _get_pre_tool_call_directive_details,
        discover_plugins,
        get_plugin_manager,
    )
    from tools.registry import registry
    from tools.terminal_tool import set_approval_callback

    discover_plugins()
    asked = []

    def answer(command, description, **kwargs):
        asked.append(description)
        return "always" if len(asked) in (1, 3) else "deny"

    def runs():
        log = bindir / "calls.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def count(needle):
        return sum(needle in item for item in runs())

    def call(name, args, session_id):
        raw = registry.dispatch(name, args, session_id=session_id, task_id="task")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw[:240]}
        return raw if isinstance(raw, dict) else {"raw": str(raw)[:240]}

    infer_args = {"model": "facebook/opt-125m", "prompt": "Say yes.", "max_new_tokens": 4}
    verify_args = {"receipt_path": str(receipt)}
    report = {"error": "", "cases": {}}
    try:
        if registry.get_entry("ree_infer") is None or registry.get_entry("ree_verify_receipt") is None:
            errors = {}
            try:
                for key, loaded in get_plugin_manager()._plugins.items():
                    if getattr(loaded, "error", None):
                        errors[str(key)] = str(loaded.error)[:500]
            except Exception as exc:
                errors["lookup"] = type(exc).__name__
            report["error"] = "plugin tools did not load"
            report["load_errors"] = errors
            print(json.dumps(report))
            raise SystemExit(0)
        details = _get_pre_tool_call_directive_details(
            "ree_infer", infer_args, session_id="shape", task_id="task",
        )
        report["directive"] = {
            "action": details.action,
            "rule_key": details.rule_key,
            "message": details.message or "",
        }
        set_approval_callback(answer)
        first, _modified = _dispatch_pre_tool_call_hooks(
            "ree_infer", infer_args, session_id="person", task_id="task",
        )
        inferred = call("ree_infer", infer_args, "person") if first is None else {"skipped": first}
        second, _modified = _dispatch_pre_tool_call_hooks(
            "ree_infer", infer_args, session_id="again", task_id="task",
        )
        report["person"] = {
            "first_block": first,
            "second_block": second,
            "asked": list(asked),
            "infer_level": inferred.get("level"),
            "infer_error": inferred.get("error_type"),
            "run_all": count("run-all"),
            "verify": count("verify"),
        }
        verify_block, _modified = _dispatch_pre_tool_call_hooks(
            "ree_verify_receipt", verify_args, session_id="verify", task_id="task",
        )
        verified = call("ree_verify_receipt", verify_args, "verify") if verify_block is None else {"skipped": verify_block}
        baseline = {"run_all": count("run-all"), "verify": count("verify"), "validate": count("validate"), "asked": len(asked)}
        report["verify_person"] = {
            "block": verify_block,
            "level": verified.get("level"),
            "error": verified.get("error_type"),
            "asked_tail": asked[-1] if asked else "",
            "baseline": baseline,
        }

        def unattended(label, prepare, restore):
            before_asked = len(asked)
            before_all = count("run-all")
            before_verify = count("verify")
            before_validate = count("validate")
            prepare()
            try:
                block, _modified = _dispatch_pre_tool_call_hooks(
                    "ree_infer", infer_args, session_id=label, task_id="task",
                )
                body = call("ree_infer", infer_args, label)
                verify_only, _modified = _dispatch_pre_tool_call_hooks(
                    "ree_verify_receipt", verify_args, session_id=label + "-v", task_id="task",
                )
            finally:
                restore()
            report["cases"][label] = {
                "block": block,
                "verify_block": verify_only,
                "error": body.get("error_type"),
                "asked_grew": len(asked) != before_asked,
                "run_all": count("run-all"),
                "verify": count("verify"),
                "validate": count("validate"),
                "before_all": before_all,
                "before_verify": before_verify,
                "before_validate": before_validate,
            }

        def env_on(name, value):
            os.environ[name] = value

        def env_off(name):
            os.environ.pop(name, None)

        unattended("cron", lambda: env_on("HERMES_CRON_SESSION", "1"), lambda: env_off("HERMES_CRON_SESSION"))
        unattended(
            "single",
            lambda: env_on("HERMES_SINGLE_QUERY_SESSION", "1"),
            lambda: env_off("HERMES_SINGLE_QUERY_SESSION"),
        )
        unattended(
            "webhook",
            lambda: env_on("HERMES_SESSION_PLATFORM", "webhook"),
            lambda: env_off("HERMES_SESSION_PLATFORM"),
        )
        unattended(
            "api_server",
            lambda: env_on("HERMES_SESSION_PLATFORM", "api_server"),
            lambda: env_off("HERMES_SESSION_PLATFORM"),
        )
        unattended(
            "msgraph",
            lambda: env_on("HERMES_SESSION_PLATFORM", "msgraph_webhook"),
            lambda: env_off("HERMES_SESSION_PLATFORM"),
        )
        unattended(
            "host",
            lambda: env_on("HERMES_PLUGIN_HOST_PROCESS", "1"),
            lambda: env_off("HERMES_PLUGIN_HOST_PROCESS"),
        )

        def context_case(label, var_name, value):
            from gateway.session_context import _VAR_MAP
            token = _VAR_MAP[var_name].set(value)

            def prepare():
                return None

            def restore():
                _VAR_MAP[var_name].reset(token)

            # The token is already set. prepare/restore only bookend the calls.
            unattended(label, prepare, restore)

        try:
            context_case("cron_context", "HERMES_CRON_SESSION", "1")
            context_case("webhook_context", "HERMES_SESSION_PLATFORM", "webhook")
        except Exception as exc:
            report["context_error"] = type(exc).__name__ + ": " + str(exc)

        try:
            from cron.execution_identity import enter_cron_execution, exit_cron_execution
            token = enter_cron_execution(
                {"id": "job", "name": "ree"},
                "exec-1",
                {"source": "builtin", "started_at": "2026-11-06T00:00:00Z"},
            )
            try:
                unattended("cron_mark", lambda: None, lambda: None)
            finally:
                exit_cron_execution(token)
        except Exception as exc:
            report["mark_error"] = type(exc).__name__ + ": " + str(exc)

        def bypass(label, prepare, restore, tool, args):
            before_all = count("run-all")
            before_verify = count("verify")
            before_validate = count("validate")
            before_asked = len(asked)
            prepare()
            try:
                block, _modified = _dispatch_pre_tool_call_hooks(
                    tool, args, session_id="person", task_id="task",
                )
                body = call(tool, args, "person") if block is None else {"skipped": True}
            finally:
                restore()
            report["cases"][label] = {
                "block": block,
                "level": body.get("level"),
                "error": body.get("error_type"),
                "asked_grew": len(asked) != before_asked,
                "run_all": count("run-all"),
                "verify": count("verify"),
                "validate": count("validate"),
                "before_all": before_all,
                "before_verify": before_verify,
                "before_validate": before_validate,
            }

        from tools.approval import disable_session_yolo, enable_session_yolo
        from tools.approval_context import reset_current_session_key, set_current_session_key
        from gateway.hosted_room_execution_policy import (
            POLICY_VERSION, RoomExecutionPolicy, _policy_digest,
            bind_room_execution_policy, reset_room_execution_policy,
        )
        key_token = set_current_session_key("room-1")
        try:
            bypass(
                "session_yolo",
                lambda: enable_session_yolo("room-1"),
                lambda: disable_session_yolo("room-1"),
                "ree_infer", infer_args,
            )
            bypass(
                "session_yolo_verify",
                lambda: enable_session_yolo("room-1"),
                lambda: disable_session_yolo("room-1"),
                "ree_verify_receipt", verify_args,
            )
            unsigned = {
                "version": POLICY_VERSION,
                "target_profile": "default",
                "enabled_toolsets": ["bot_room"],
                "approval_mode": "off",
                "max_iterations": 1,
            }
            policy = RoomExecutionPolicy.from_mapping({
                **unsigned, "policy_digest": _policy_digest(unsigned),
            })
            room_token = bind_room_execution_policy(policy)
            try:
                bypass("room_off", lambda: None, lambda: None, "ree_infer", infer_args)
            finally:
                reset_room_execution_policy(room_token)
        finally:
            reset_current_session_key(key_token)
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        set_approval_callback(None)
    print(json.dumps(report))
    raise SystemExit(0)

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _refused(text):
    return isinstance(text, str) and text.startswith("BLOCKED:") and "even after always" in text and "cannot start REE" in text


def test_public_hook_asks_a_person_and_refuses_after_always():
    pytest.importorskip("hermes_cli.plugins")
    env = {key: value for key, value in os.environ.items() if not key.startswith("HERMES_")}
    env["REE_PUBLIC_CHILD"] = "1"
    proc = subprocess.run(
        [sys.executable, __file__, str(ROOT)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(item for item in reversed(proc.stdout.splitlines()) if item.startswith("{"))
    report = json.loads(line)
    assert not report.get("error"), report
    directive = report["directive"]
    assert directive["action"] == "approve", report
    assert directive["rule_key"].startswith("ree_infer:facebook/opt-125m:")
    assert "Infer" in directive["message"] and "Choosing always" in directive["message"]
    person = report["person"]
    assert person["first_block"] is None, report
    assert person["asked"] and "Choosing always" in person["asked"][0]
    assert "facebook/opt-125m" in person["asked"][0]
    assert person["infer_level"] == "inferred", report
    assert person["run_all"] == 1, report
    assert person["second_block"], report
    assert len(person["asked"]) == 2
    assert "Choosing always" in person["asked"][1]
    verify = report["verify_person"]
    assert verify["block"] is None, report
    assert "Re-execute" in verify["asked_tail"] and "Choosing always" in verify["asked_tail"]
    assert verify["level"] == "reexecuted_and_text_match" or verify["level"] == "reexecuted", report
    assert verify["baseline"]["verify"] >= 1, report
    for label in ("cron", "single", "webhook", "api_server", "msgraph", "host"):
        case = report["cases"][label]
        assert _refused(case["block"]), case
        assert _refused(case["verify_block"]), case
        assert case["asked_grew"] is False, case
        assert case["run_all"] == case["before_all"], case
        assert case["verify"] == case["before_verify"], case
        assert case["validate"] == case["before_validate"], case
        assert case["error"] == "approval_unavailable", case
    for label in ("cron_context", "webhook_context", "cron_mark"):
        assert label in report["cases"], report
        case = report["cases"][label]
        assert _refused(case["block"]), case
        assert case["asked_grew"] is False, case
        assert case["run_all"] == case["before_all"], case
        assert case["verify"] == case["before_verify"], case
    for label in ("session_yolo", "session_yolo_verify", "room_off"):
        case = report["cases"][label]
        assert case["block"] is None, case
        assert case["asked_grew"] is False, case
        assert case["error"] == "approval_unavailable", case
        assert case["level"] is None, case
        assert case["run_all"] == case["before_all"], case
        assert case["verify"] == case["before_verify"], case
    yolo_verify = report["cases"]["session_yolo_verify"]
    assert yolo_verify["validate"] - yolo_verify["before_validate"] <= 1, yolo_verify
