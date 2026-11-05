from __future__ import annotations

import gate


def _quiet(monkeypatch):
    monkeypatch.setenv("HERMES_INTERACTIVE", "1")
    for name in (
        "HERMES_CRON_SESSION",
        "HERMES_SINGLE_QUERY_SESSION",
        "HERMES_SESSION_PLATFORM",
        "HERMES_YOLO_MODE",
        "HERMES_PLUGIN_HOST_PROCESS",
        "HERMES_GATEWAY_SESSION",
        "HERMES_EXEC_ASK",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gate, "_approvals_off", lambda: False)
    monkeypatch.setattr(gate, "_cron_reader", lambda: None)
    gate.clear_room("s", "t")


def test_each_call_asks_with_a_new_key(monkeypatch):
    _quiet(monkeypatch)
    first = gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")
    second = gate.issue("infer", "Qwen/Qwen2.5-0.5B", 8, session_id="s", task_id="t")
    assert first["action"] == "approve"
    assert second["action"] == "approve"
    assert first["rule_key"] != second["rule_key"]
    assert first["rule_key"].startswith("ree_verify:facebook/opt-125m:")
    assert "Re-execute" in first["message"]
    assert "Infer" in second["message"]
    assert "not limited to Hugging Face" in first["message"]
    assert "Choosing always" in first["message"]
    assert "Takes minutes" in first["message"]
    assert "receipt file" in first["message"]
    assert "no receipt file" in second["message"]
    assert "cache token file visible in container." in first["message"]
    longest = gate.question("infer", "Qwen/Qwen2.5-0.5B", 256)
    assert len(first["message"]) <= 300
    assert len(second["message"]) <= 300
    assert len(longest) <= 300
    assert "`" not in longest
    assert "\n" not in first["message"]
    gate.note_response(pattern_key="plugin_rule:" + first["rule_key"], choice="once")
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is True
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is False


def test_human_grant_is_required(monkeypatch):
    _quiet(monkeypatch)
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False
    gate.note_response(pattern_key="plugin_rule:" + decision["rule_key"], choice="once")
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    gate.note_response(pattern_key="plugin_rule:" + decision["rule_key"], choice="deny")
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    gate.note_response(
        pattern_key="plugin_rule:" + decision["rule_key"], choice="once", decided_by="aux_llm",
    )
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    gate.note_response(pattern_key="plugin_rule:other", choice="always")
    gate.note_response(
        pattern_key="plugin_rule:" + decision["rule_key"],
        pattern_keys=["plugin_rule:" + decision["rule_key"]],
        choice="session",
    )
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is True
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    gate.note_response(pattern_key="ree_infer:facebook/opt-125m:not-the-prefix", choice="always")
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False
    decision = gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")
    gate.note_response(pattern_key="plugin_rule:" + decision["rule_key"], choice="always")
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is True


def test_unattended_contexts_do_not_ask(monkeypatch):
    cases = (
        ("HERMES_CRON_SESSION", "1"),
        ("HERMES_YOLO_MODE", "1"),
        ("HERMES_SINGLE_QUERY_SESSION", "1"),
        ("HERMES_SESSION_PLATFORM", "webhook"),
        ("HERMES_SESSION_PLATFORM", "api_server"),
        ("HERMES_SESSION_PLATFORM", "msgraph_webhook"),
    )
    for name, value in cases:
        _quiet(monkeypatch)
        gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")
        monkeypatch.setenv(name, value)
        decision = gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")
        allowed, message = gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")
        assert decision["action"] == "block", name
        assert decision["message"].startswith("BLOCKED:")
        assert allowed is False
        assert message.startswith("BLOCKED:")
    _quiet(monkeypatch)
    monkeypatch.setattr(gate, "_approvals_off", lambda: True)
    assert gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")["action"] == "block"
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is False


def test_stored_permit_does_not_survive_cron(monkeypatch):
    _quiet(monkeypatch)
    assert gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")["action"] == "approve"
    monkeypatch.setenv("HERMES_CRON_SESSION", "1")
    allowed, message = gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    assert allowed is False
    assert "even after always" in message
    monkeypatch.delenv("HERMES_CRON_SESSION", raising=False)
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False


def test_refusal_does_not_say_nothing_ran(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    allowed, message = gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")
    assert allowed is False
    assert "nothing ran" not in message
    assert "refused" in message


def test_host_isolation_does_not_ask(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    decision = gate.issue("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")
    assert decision["action"] == "block"
    assert gate.approve("infer", "facebook/opt-125m", 1, session_id="s", task_id="t")[0] is False


def test_cut_or_broken_question_is_not_sent(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(gate, "question", lambda *args, **kwargs: "x" * 400)
    assert gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")["action"] == "block"
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is False
    monkeypatch.setattr(gate, "question", lambda *args, **kwargs: "line\nbreak")
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is False


def test_missing_permit_fails_closed(monkeypatch):
    _quiet(monkeypatch)
    allowed, message = gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")
    assert allowed is False
    assert message.startswith("BLOCKED:")
    assert "not obtained" in message or "approval was not obtained" in message


def test_cron_mark_and_unreadable_mark_block(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.setattr(gate, "_cron_reader", lambda: (lambda: {"id": "job"}))
    assert gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")["action"] == "block"
    def boom():
        raise RuntimeError("unread")
    monkeypatch.setattr(gate, "_cron_reader", lambda: boom)
    assert "could not be read" in gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")["message"]


def test_nobody_present_does_not_ask(monkeypatch):
    _quiet(monkeypatch)
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    assert gate.issue("verify", "facebook/opt-125m", session_id="s", task_id="t")["action"] == "block"
    assert gate.approve("verify", "facebook/opt-125m", session_id="s", task_id="t")[0] is False
