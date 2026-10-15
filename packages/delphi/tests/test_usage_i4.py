"""Typed refusals from the argument table, plus the recorded sessions."""
from __future__ import annotations

import json

import pytest

from contract import ONE_OF, TABLES, argument_refusal
from schemas import DESCRIPTIONS
from service import dispatch
from spec import PROBLEMS, TYPES

ADDRESS = "0x" + "11" * 20
PLANTED = "PLANTED_VALUE_i4"
TOOLS = tuple(DESCRIPTIONS)
ADDED = ("field", "problem", "expected", "allowed_fields")


def _ask(tool, params):
    text = dispatch(
        tool, params, caller=lambda *args, **kwargs: {"ok": False}, reserve_fn=lambda count: True,
    )
    return json.loads(text)


def _base(tool):
    if tool == "delphi_get_market":
        return {"market_id": ADDRESS}
    if tool == "delphi_compute_edge":
        return {"your_probability": "0.4", "implied_probability": "0.5"}
    if tool == "delphi_query_subgraph":
        return {"mode": "meta"}
    if tool in ("delphi_quote_buy", "delphi_quote_sell"):
        return {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"}
    return {}


def _table(tool):
    return "args." + tool.removeprefix("delphi_")


def _kind(tool, arg):
    return TABLES[_table(tool)][arg]["type"]


def _grouped(tool, arg):
    return any(arg in group for group in ONE_OF.get(_table(tool), ()))


def _bad(kind, problem):
    if problem == "wrong_type":
        return 1.5
    if problem == "out_of_range":
        return {"limit": 51, "first": 50, "skip": 10001, "outcome_index": 2**31}[kind]
    if problem == "bad_format":
        if kind == "address":
            return "0x" + PLANTED
        if kind == "user_probability":
            return PLANTED
        if kind == "share_amount":
            return PLANTED
        return PLANTED
    return None


def _applicable(tool, arg, problem):
    kind = _kind(tool, arg)
    spec = TABLES[_table(tool)][arg]
    if problem == "unknown_field":
        return True
    if problem == "missing":
        return spec.get("required", True) and not _grouped(tool, arg)
    if problem == "wrong_type":
        return True
    if problem == "out_of_range":
        return kind in ("limit", "first", "skip", "outcome_index")
    if problem == "bad_format":
        return kind not in ("bool", "limit", "first", "skip", "outcome_index")
    if problem == "conflict":
        return _grouped(tool, arg)
    return False


def _payload(tool, arg, problem):
    if tool == "delphi_query_subgraph" and arg != "mode":
        params = {"mode": "trades", "market_address": ADDRESS, "first": 1, "skip": 0}
    elif tool == "delphi_compute_edge" and arg in ("market_id", "market_address", "outcome_idx"):
        params = {"your_probability": "0.4", "outcome_idx": 0, "market_id": ADDRESS}
        if arg == "market_address":
            params.pop("market_id")
            params["market_address"] = ADDRESS
    elif tool == "delphi_get_market" and arg == "market_address":
        params = {"market_address": ADDRESS}
    elif tool in ("delphi_quote_buy", "delphi_quote_sell") and arg in ("market_id", "market_address"):
        params = {"outcome_idx": 0, "shares": "1", arg: ADDRESS}
    else:
        params = _base(tool)
    kind = _kind(tool, arg)
    if problem == "missing":
        params.pop(arg, None)
        return params, None
    if problem == "conflict":
        if tool == "delphi_get_market":
            return {"market_id": ADDRESS, "market_address": ADDRESS}, ADDRESS
        if tool in ("delphi_quote_buy", "delphi_quote_sell"):
            return {
                "market_id": ADDRESS, "market_address": ADDRESS,
                "outcome_idx": 0, "shares": "1",
            }, ADDRESS
        return {
            "your_probability": "0.4", "implied_probability": "0.5",
            "market_id": ADDRESS, "outcome_idx": 0,
        }, ADDRESS
    if problem == "unknown_field":
        params["not_a_field"] = PLANTED
        return params, PLANTED
    params[arg] = _bad(kind, problem)
    planted = PLANTED if isinstance(params[arg], str) and PLANTED in params[arg] else None
    if planted is None and problem == "out_of_range":
        planted = str(params[arg])
    if planted is None and problem == "wrong_type" and not isinstance(params[arg], str):
        planted = "1.5" if params[arg] == 1.5 else None
    return params, planted


def _cases():
    rows = []
    for tool in TOOLS:
        for arg in TABLES[_table(tool)]:
            for problem in PROBLEMS:
                rows.append((tool, arg, problem))
    return rows


@pytest.mark.parametrize("tool,arg,problem", _cases())
def test_every_tool_argument_and_problem(tool, arg, problem):
    if not _applicable(tool, arg, problem):
        found = argument_refusal(_table(tool), _base(tool))
        assert found is None or found[1] != problem
        return
    params, planted = _payload(tool, arg, problem)
    body = _ask(tool, params)
    assert body["error_type"] == "invalid_argument"
    assert body["problem"] == problem
    assert body["field"]
    assert set(body["allowed_fields"]) == set(TABLES[_table(tool)])
    blob = json.dumps({key: body[key] for key in ADDED})
    if planted:
        assert planted not in blob
    assert body["message"] == "The arguments did not match."


def test_recorded_sessions_do_not_echo_values():
    first = _ask("delphi_query_subgraph", {"first": 50, "mode": "trades"})
    assert first["field"] == "market_address" and first["problem"] == "missing"
    assert "50" not in json.dumps({key: first[key] for key in ADDED})
    second = _ask("delphi_query_subgraph", {
        "first": 50, "market_address": ADDRESS, "mode": "trades",
    })
    assert second["field"] == "first" and second["problem"] == "out_of_range"
    assert "50" not in json.dumps({key: second[key] for key in ADDED})
    assert ADDRESS not in json.dumps({key: second[key] for key in ADDED})
    edge = _ask("delphi_compute_edge", {
        "market_id": ADDRESS, "outcome_idx": 0.0, "your_probability": "0.7",
    })
    assert edge["field"] == "outcome_idx" and edge["problem"] == "wrong_type"
    assert "0.0" not in json.dumps(edge)
    live = _ask("delphi_compute_edge", {
        "market_address": ADDRESS, "outcome_idx": 0, "your_probability": "0.7",
    })
    assert live["error_type"] == "config"
    assert live["missing"] == ["DELPHI_API_ACCESS_KEY"]
    assert "delphi_compute_edge" in live["works_without_key"]
    assert ADDRESS not in json.dumps(live)
    quote = argument_refusal("args.quote_buy", {
        "market_address": ADDRESS, "outcome_idx": 1, "shares": "10",
    })
    assert quote is None
    uuid = _ask("delphi_get_market", {"market_id": "11111111-1111-4111-8111-111111111111"})
    assert uuid["problem"] == "bad_format"
    assert "11111111" not in json.dumps({key: uuid[key] for key in ADDED})


def test_config_lists_names_not_values(monkeypatch):
    monkeypatch.delenv("DELPHI_API_ACCESS_KEY", raising=False)
    monkeypatch.setenv("DELPHI_WALLET_ADDRESS", PLANTED)
    body = _ask("delphi_get_positions", {"limit": 50, "wallet": ADDRESS})
    assert body["error_type"] == "config"
    assert body["missing"] == ["DELPHI_API_ACCESS_KEY"]
    assert body["needed_for"] == "delphi_get_positions"
    assert "delphi_quote_buy" in body["works_without_key"]
    assert "delphi_compute_edge" in body["works_without_key"]
    assert PLANTED not in json.dumps(body)
    assert ADDRESS not in json.dumps(body)


def test_descriptions_name_the_real_arguments():
    for name, text in DESCRIPTIONS.items():
        assert text.startswith("Returns ")
        assert "Read-only." in text
        for token in ("delphi_get_market", "market_id", "market_address", "outcome_idx"):
            if token in text:
                assert token in DESCRIPTIONS or token in TABLES[_table(name)] or token == name
    buy = DESCRIPTIONS["delphi_quote_buy"]
    assert "outcome_idx starts at 0" in buy
    assert "delphi_get_market" in buy
    assert "without a key, the name is unknown" in buy
    edge = DESCRIPTIONS["delphi_compute_edge"]
    assert "No key for implied_probability." in edge
    assert "Key required for market_id or market_address." in edge
    assert TYPES["address"]["expected"] == "0x and 40 hex characters"
