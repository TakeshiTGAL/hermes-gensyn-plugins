"""Call the seven tools through each Hermes host's real registry.dispatch."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
# Optional: a colon-separated list of Python interpreters that have Hermes installed.
PYTHONS = tuple(Path(p) for p in os.environ.get("HERMES_TEST_PYTHONS", "").split(":") if p)
SKIP_MARK = "SKIP hermes-core-absent"


def host_interpreters(pythons, hermes_repo, executable):
    """Prefer the two local hosts. Otherwise use the checked-out Hermes."""
    found = [str(path) for path in pythons if Path(path).is_file()]
    if found:
        return found
    if hermes_repo and Path(hermes_repo).is_dir():
        return [executable]
    return []


def test_string_scalars_are_not_schema_types():
    from schemas import SCHEMAS
    props = SCHEMAS["delphi_list_markets"]["parameters"]["properties"]
    assert props["limit"].get("type") != "integer"
    assert props["limit"]["anyOf"][0]["type"] == "integer"
    assert props["verifiable"].get("type") != "boolean"
    assert props["verifiable"]["anyOf"][0]["type"] == "boolean"


def test_tools_do_not_replace_the_hermes_entry():
    source = (PACKAGE / "tools.py").read_text()
    assert "model_tools" not in source
    assert "handle_function_call" not in source
    phrase = (
        "Hermes turns an argument that is not an object into an empty object "
        "before the tool sees it. When that empty object omits a required "
        "field, the tool rejects the call as missing."
    )
    for path in (PACKAGE / "README.md", PACKAGE / "skills" / "delphi" / "SKILL.md"):
        flat = " ".join(path.read_text().split())
        assert phrase in flat
        assert "for every tool" not in flat


def test_absent_hermes_core_is_marked_skip(monkeypatch):
    monkeypatch.setattr(f"{__name__}.host_interpreters", lambda *_args: [])
    with pytest.raises(pytest.skip.Exception) as caught:
        test_both_hermes_hosts_dispatch_five_tools()
    assert SKIP_MARK in str(caught.value)


def test_checked_out_hermes_is_not_skipped(tmp_path):
    repo = tmp_path / "hermes-agent"
    repo.mkdir()
    assert host_interpreters([], str(repo), sys.executable) == [sys.executable]


def test_both_hermes_hosts_dispatch_five_tools():
    interpreters = host_interpreters(
        PYTHONS, os.environ.get("HERMES_AGENT_REPO"), sys.executable,
    )
    if not interpreters:
        pytest.skip(SKIP_MARK)
    for python in interpreters:
        env = os.environ.copy()
        home = tempfile.mkdtemp(prefix="delphi-host-")
        env["HERMES_HOME"] = home
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("DELPHI_API_ACCESS_KEY", None)
        try:
            proc = subprocess.run(
                [str(python), str(Path(__file__).resolve()), "host-call"],
                cwd=PACKAGE,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        finally:
            shutil.rmtree(home, ignore_errors=True)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        report = json.loads(proc.stdout)
        assert report["ok"] is True
        assert report["failures"] == 7
        assert report["tools"] == [
            "delphi_compute_edge",
            "delphi_get_market",
            "delphi_get_positions",
            "delphi_list_markets",
            "delphi_query_subgraph",
            "delphi_quote_buy",
            "delphi_quote_sell",
        ]


def host_call():
    # model_tools._execute_tool passes task_id, session_id, and user_task into
    # registry.dispatch. v2026.9.21 then calls handler(args, **kwargs) unfiltered.
    from tools.registry import registry

    sys.path.insert(0, str(PACKAGE))
    import service
    from schemas import SCHEMAS
    from tests.support import ADDRESS, WALLET, market, meta, position, success

    spec = importlib.util.spec_from_file_location(
        "delphi_plugin_tools", PACKAGE / "tools.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["delphi_plugin_tools"] = module
    spec.loader.exec_module(module)
    os.environ["DELPHI_API_ACCESS_KEY"] = "host-probe-key"
    os.environ["DELPHI_NETWORK"] = "testnet"
    os.environ["DELPHI_WALLET_ADDRESS"] = WALLET

    def fake(op, args, *, needs_key, budget, network):
        pages = {
            "list_markets": {"markets": [market()]},
            "get_market": market(),
            "get_positions": {"positions": [position()]},
            "subgraph_meta": meta(),
            "quote_buy": {"amount_raw": "1", "decimals": {"status": "unavailable"}},
            "quote_sell": {"amount_raw": "1", "decimals": {"status": "unavailable"}},
        }
        if op not in pages:
            raise AssertionError(op)
        return success(pages[op], outbound=budget)

    service.dispatch.__kwdefaults__["caller"] = fake
    for name, schema in SCHEMAS.items():
        registry.register(
            name=name,
            toolset="hermes-gensyn-delphi",
            schema=schema,
            handler=module.HANDLERS[name],
            description=schema["description"],
        )
    calls = [
        ("delphi_list_markets", {}),
        ("delphi_get_market", {"market_id": ADDRESS}),
        ("delphi_get_positions", {"wallet": WALLET}),
        ("delphi_query_subgraph", {"mode": "meta"}),
        (
            "delphi_compute_edge",
            {"implied_probability": "0.4", "your_probability": "0.5"},
        ),
        (
            "delphi_quote_buy",
            {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"},
        ),
        (
            "delphi_quote_sell",
            {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"},
        ),
    ]
    import model_tools
    names = []
    for name, args in calls:
        raw = model_tools.handle_function_call(name, args, task_id="t", session_id="s")
        if not isinstance(raw, str):
            raise SystemExit(repr(raw))
        body = json.loads(raw)
        if body.get("ok") is not True:
            raise SystemExit(raw)
        names.append(name)
    failures = (
        ("delphi_list_markets", {"status": "nope"}, None),
        ("delphi_get_market", {}, "market_id"),
        ("delphi_get_positions", {"wallet": "not-an-address"}, "wallet"),
        ("delphi_query_subgraph", {"mode": "trades"}, "market_address"),
        ("delphi_compute_edge", {"market_id": ADDRESS, "your_probability": "0.5"}, "outcome_idx"),
        ("delphi_quote_buy", {"market_address": ADDRESS, "outcome_idx": 0, "shares": "0"}, "shares"),
        ("delphi_quote_sell", {"market_address": ADDRESS, "outcome_idx": 0}, "shares"),
    )
    for name, args, field in failures:
        raw = model_tools.handle_function_call(name, args, task_id="t", session_id="s")
        body = json.loads(raw)
        if body.get("ok") is not False or body.get("error_type") != "invalid_argument":
            raise SystemExit(raw[:400])
        if field and body.get("field") != field:
            raise SystemExit(raw[:400])
    entered = model_tools.handle_function_call(
        "delphi_get_market", {"market_id": ADDRESS}, task_id="t", session_id="s",
    )
    body = json.loads(entered)
    if body.get("ok") is not True or "creator_notice" not in body:
        raise SystemExit(entered[:400])
    refused = model_tools.handle_function_call(
        "delphi_list_markets", {"status": "nope"}, task_id="t", session_id="s",
    )
    bad = json.loads(refused)
    if bad.get("error_type") != "invalid_argument" or "nope" in refused:
        raise SystemExit(refused[:400])
    service.dispatch.__kwdefaults__["caller"] = lambda op, args, **_rest: success(
        {"id": ADDRESS, "spotImpliedProbabilities": ["0.4", "0.6"]}, outbound=3,
    ) if op == "live_edge" else fake(op, args, **_rest)
    ranged = model_tools.handle_function_call(
        "delphi_compute_edge",
        {"market_id": ADDRESS, "outcome_idx": 7, "your_probability": "0.5"},
        task_id="t", session_id="s",
    )
    edge = json.loads(ranged)
    if edge.get("error_type") != "invalid_argument" or edge.get("field") != "outcome_idx":
        raise SystemExit(ranged[:400])
    if edge.get("problem") != "out_of_range" or "7" in ranged:
        raise SystemExit(ranged[:400])
    strings = (
        ("delphi_list_markets", {"limit": "5"}, "limit"),
        ("delphi_list_markets", {"verifiable": "true"}, "verifiable"),
    )
    for name, args, field in strings:
        raw = model_tools.handle_function_call(name, args, task_id="t", session_id="s")
        body = json.loads(raw)
        if body.get("error_type") != "invalid_argument" or body.get("field") != field:
            raise SystemExit(raw[:400])
        if body.get("problem") != "wrong_type":
            raise SystemExit(raw[:400])
    for name in names:
        raw = module.HANDLERS[name]([])
        body = json.loads(raw)
        if body.get("ok") is not False or body.get("error_type") != "invalid_argument":
            raise SystemExit(raw[:400])
        if body.get("problem") != "wrong_type" or body.get("expected") != "an object":
            raise SystemExit(raw[:400])
    print(json.dumps({"ok": True, "tools": sorted(names), "failures": len(failures)}))


if __name__ == "__main__" and sys.argv[1:] == ["host-call"]:
    host_call()
