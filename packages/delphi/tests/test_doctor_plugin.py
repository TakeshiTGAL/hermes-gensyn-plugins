from __future__ import annotations

import json
import sys

import pytest
from agent.secret_scope import reset_secret_scope, set_multiplex_active, set_secret_scope

import doctor
from process import ChildError, ChildResult


class Context:
    def __init__(self):
        self.tools = []
        self.hooks = []
        self.skills = []
        self.commands = []

    def get_config(self, name):
        return {"network": "testnet", "wallet_address": ""}.get(name)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, name, handler):
        self.hooks.append((name, handler))

    def register_skill(self, *args, **kwargs):
        self.skills.append((args, kwargs))

    def register_cli_command(self, **kwargs):
        self.commands.append(kwargs)


def test_registration_has_exactly_five_tools_and_transform_hook(monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "delphi_plugin",
        path,
        submodule_search_locations=[str(path.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ctx = Context()
    module.register(ctx)
    assert sorted(item["name"] for item in ctx.tools) == [
        "delphi_compute_edge",
        "delphi_get_market",
        "delphi_get_positions",
        "delphi_list_markets",
        "delphi_query_subgraph",
        "delphi_quote_buy",
        "delphi_quote_sell",
    ]
    assert [name for name, _ in ctx.hooks] == ["transform_tool_result"]
    assert len(ctx.commands) == 1


def good_runner(argv, request, env, deadline):
    assert argv[-1] == "--version"
    assert request == b""
    assert "DELPHI_API_ACCESS_KEY" not in env
    assert deadline <= 5
    return ChildResult(0, b"v20.18.0\n", b"")


def test_doctor_is_offline_and_healthy_with_required_configuration(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "SECRET-MARKER")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    monkeypatch.setenv("DELPHI_WALLET_ADDRESS", "0x" + "ab" * 20)
    result = doctor.run_doctor(runner=good_runner, node_path="/fake/node")
    assert result["overall"] == "healthy"
    assert result["sdk"]["version"] == "2.1.0"
    assert "SECRET-MARKER" not in json.dumps(result)


@pytest.mark.parametrize(
    "change,check",
    [
        ({"DELPHI_API_ACCESS_KEY": None}, "api_key"),
        ({"DELPHI_NETWORK": "devnet"}, "network"),
        ({"DELPHI_WALLET_ADDRESS": "bad"}, "wallet"),
    ],
)
def test_doctor_fails_closed_for_configuration(monkeypatch, change, check):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    monkeypatch.setenv("DELPHI_WALLET_ADDRESS", "0x" + "ab" * 20)
    for name, value in change.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    result = doctor.run_doctor(runner=good_runner, node_path="/fake/node")
    assert result["overall"] == "error"
    assert result[check]["status"] == "error"


def test_doctor_reads_plugin_settings_when_environment_is_unset(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured")
    monkeypatch.delenv("DELPHI_NETWORK", raising=False)
    monkeypatch.delenv("DELPHI_WALLET_ADDRESS", raising=False)
    from settings import bind_config

    bind_config(
        lambda name: {"network": "mainnet", "wallet_address": "not-an-address"}.get(name)
    )
    try:
        result = doctor.run_doctor(runner=good_runner, node_path="/fake/node")
    finally:
        bind_config(None)
    assert result["overall"] == "error"
    assert result["network"]["value"] == "mainnet"
    assert result["wallet"]["status"] == "error"
    assert result["wallet"]["message"] == "The configured wallet address is invalid."
    assert result["wallet"]["setting"] == "DELPHI_WALLET_ADDRESS"
    assert result["wallet"]["problem"] == "invalid"
    assert "not-an-address" not in json.dumps(result)


def test_invalid_scope_does_not_blame_the_process_environment(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "from-env")
    monkeypatch.setenv("DELPHI_NETWORK", "mainnet")
    monkeypatch.setenv("DELPHI_WALLET_ADDRESS", "0x" + "ab" * 20)
    set_multiplex_active(True)
    token = set_secret_scope({
        "DELPHI_NETWORK": "not-a-network",
        "DELPHI_WALLET_ADDRESS": "bad",
    })
    try:
        result = doctor.run_doctor(runner=good_runner, node_path="/fake/node")
    finally:
        reset_secret_scope(token)
        set_multiplex_active(False)
    assert doctor._INVALID == {
        "network": ("DELPHI_NETWORK", "The configured network is invalid."),
        "wallet": ("DELPHI_WALLET_ADDRESS", "The configured wallet address is invalid."),
    }
    for check, (setting, message) in doctor._INVALID.items():
        body = result[check]
        assert body["status"] == "error"
        assert body["setting"] == setting
        assert body["problem"] == "invalid"
        assert body["message"] == message
        assert not body["message"].startswith(setting)
    assert result["api_key"]["status"] == "error"
    assert "from-env" not in json.dumps(result)


def test_doctor_rejects_sdk_version_mismatch(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "configured")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    result = doctor.run_doctor(
        runner=good_runner,
        node_path="/fake/node",
        sdk_version="9.9.9",
    )
    assert result["sdk"]["status"] == "error"
    assert result["overall"] == "error"


def test_doctor_structures_node_failure(monkeypatch):
    def failed(*_args, **_kwargs):
        raise ChildError("timeout", "late")

    result = doctor.run_doctor(runner=failed, node_path="/fake/node")
    assert result["node"]["status"] == "error"
    assert result["overall"] == "error"


def test_doctor_cli_serializes_result(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "run_doctor", lambda: {"overall": "healthy"})
    assert doctor.doctor_main() == 0
    assert json.loads(capsys.readouterr().out) == {"overall": "healthy"}
