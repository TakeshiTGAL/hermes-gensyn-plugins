from __future__ import annotations

import sys
import types

import gate


def _install(monkeypatch, **flags):
    approval = types.ModuleType("tools.approval")
    context = types.ModuleType("tools.approval_context")
    package = types.ModuleType("tools")
    package.__path__ = []
    calls = []

    def request(name, text, rule_key=""):
        calls.append((name, text, rule_key))
        return {"approved": flags.get("approved", True)}

    approval.request_tool_approval = request
    approval._yolo_active = lambda: flags.get("yolo", False)
    context._is_cron_approval_context = lambda: flags.get("cron", False)
    context._get_approval_mode = lambda: flags.get("mode", "manual")
    context._is_single_query_approval_context = lambda: flags.get("single", False)
    context._is_unattended_platform_approval_context = lambda: flags.get("unattended", False)
    monkeypatch.setitem(sys.modules, "tools", package)
    monkeypatch.setitem(sys.modules, "tools.approval", approval)
    monkeypatch.setitem(sys.modules, "tools.approval_context", context)
    return calls


def test_each_call_asks_with_a_new_key(monkeypatch):
    calls = _install(monkeypatch)
    assert gate.approve("verify", "facebook/opt-125m")[0] is True
    assert gate.approve("infer", "Qwen/Qwen2.5-0.5B", 8)[0] is True
    assert calls[0][2] != calls[1][2]
    assert "Re-execute" in calls[0][1]
    assert "Infer" in calls[1][1]
    assert "not limited to Hugging Face" in calls[0][1]
    assert "Choosing always" in calls[0][1]
    assert "Takes minutes" in calls[0][1]
    assert "receipt file" in calls[0][1]
    assert "no receipt file" in calls[1][1]
    assert "cache token file visible in container." in calls[0][1]
    longest = gate.question("infer", "Qwen/Qwen2.5-0.5B", 256)
    assert len(calls[0][1]) <= 300
    assert len(calls[1][1]) <= 300
    assert len(longest) <= 300
    assert "`" not in longest
    assert "\n" not in calls[0][1]


def test_unattended_contexts_do_not_ask(monkeypatch):
    for flag in ("cron", "yolo", "single", "unattended"):
        calls = _install(monkeypatch, **{flag: True})
        allowed, message = gate.approve("verify", "facebook/opt-125m")
        assert allowed is False
        assert message.startswith("BLOCKED:")
        assert calls == []
    calls = _install(monkeypatch, mode="off")
    assert gate.approve("verify", "facebook/opt-125m")[0] is False
    assert calls == []


def test_refusal_does_not_say_nothing_ran(monkeypatch):
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    allowed, message = gate.approve("verify", "facebook/opt-125m")
    assert allowed is False
    assert "nothing ran" not in message
    assert "refused" in message


def test_host_isolation_does_not_ask(monkeypatch):
    calls = _install(monkeypatch)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    assert gate.approve("infer", "facebook/opt-125m", 1)[0] is False
    assert calls == []


def test_cut_or_broken_question_is_not_sent(monkeypatch):
    calls = _install(monkeypatch)
    monkeypatch.setattr(gate, "question", lambda *args, **kwargs: "x" * 400)
    assert gate.approve("verify", "facebook/opt-125m")[0] is False
    monkeypatch.setattr(gate, "question", lambda *args, **kwargs: "line\nbreak")
    assert gate.approve("verify", "facebook/opt-125m")[0] is False
    assert calls == []


def test_approval_exception_fails_closed(monkeypatch):
    _install(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("nope")

    sys.modules["tools.approval"].request_tool_approval = boom
    allowed, message = gate.approve("verify", "facebook/opt-125m")
    assert allowed is False
    assert message.startswith("BLOCKED:")


def test_missing_approval_api_fails_closed(monkeypatch):
    for key in list(sys.modules):
        if key == "tools" or key.startswith("tools."):
            monkeypatch.delitem(sys.modules, key, raising=False)
    real = __import__

    def blocked(name, *args, **kwargs):
        if name == "tools" or name.startswith("tools."):
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    allowed, message = gate.approve("verify", "facebook/opt-125m")
    assert allowed is False
    assert "BLOCKED:" in message
