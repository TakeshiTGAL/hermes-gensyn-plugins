from __future__ import annotations

import json

import pytest

from hooks import on_transform_tool_result
from service import _FIXED, dispatch, egress
from spec import ERROR_TYPES
from tests.support import ADDRESS, WALLET, FakeBridge, event, failure, market, meta, position, success


def call(tool, params, reply, monkeypatch, secret):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", secret)
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    monkeypatch.setenv("DELPHI_WALLET_ADDRESS", WALLET)
    text = dispatch(
        tool,
        params,
        caller=FakeBridge([reply]),
        reserve_fn=lambda count: True,
    )
    assert secret not in text
    return json.loads(text)


@pytest.mark.parametrize(
    "tool,params,reply,secret",
    [
        (
            "delphi_list_markets",
            {},
            success({"markets": [market(metadata={"question": "KEY-MARKER", "outcomes": ["Y"]})]}),
            "KEY-MARKER",
        ),
        (
            "delphi_get_market",
            {"market_id": ADDRESS},
            success(market(metadata={"question": "KEY-MARKER", "outcomes": ["Y"]})),
            "KEY-MARKER",
        ),
        (
            "delphi_get_positions",
            {"wallet": WALLET},
            success({"positions": [position(id="KEY-MARKER")]}),
            "KEY-MARKER",
        ),
        (
            "delphi_query_subgraph",
            {"mode": "meta"},
            success(meta(deployment="KEY-MARKER")),
            "KEY-MARKER",
        ),
        (
            "delphi_compute_edge",
            {"implied_probability": "0.4", "your_probability": "0.25"},
            success({}),
            "0.25",
        ),
    ],
)
def test_every_tool_rejects_secret_in_success(tool, params, reply, secret, monkeypatch):
    result = call(tool, params, reply, monkeypatch, secret)
    assert result["ok"] is False
    assert result["error_type"] == "internal"


@pytest.mark.parametrize(
    "tool,params",
    [
        ("delphi_list_markets", {}),
        ("delphi_get_market", {"market_id": ADDRESS}),
        ("delphi_get_positions", {"wallet": WALLET}),
        ("delphi_query_subgraph", {"mode": "meta"}),
        ("delphi_compute_edge", {"market_id": ADDRESS, "outcome_idx": 0, "your_probability": "0.5"}),
        ("delphi_quote_buy", {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"}),
        ("delphi_quote_sell", {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"}),
    ],
)
@pytest.mark.parametrize("kind", ERROR_TYPES)
def test_every_tool_drops_upstream_failure_text(tool, params, kind, monkeypatch):
    marker = "UPSTREAM-MARKER-SENTENCE"
    result = call(
        tool,
        params,
        {**failure(kind, f"API request failed (429): {marker} http://evil.example"), "http_status": 429},
        monkeypatch,
        "unused-secret-value",
    )
    assert result["ok"] is False
    assert result["error_type"] == kind
    assert result["message"] == f"{_FIXED[kind]} (429)"
    dumped = json.dumps(result)
    assert marker not in dumped
    assert "evil.example" not in dumped


def test_one_percent_decode_in_question_is_blocked(monkeypatch):
    secret = "synthetic-key-MARKER-012"
    encoded = "".join(f"%{ord(char):02X}" for char in secret)
    result = call(
        "delphi_get_market",
        {"market_id": ADDRESS},
        success(market(metadata={"question": encoded, "outcomes": ["Yes"]})),
        monkeypatch,
        secret,
    )
    assert result["error_type"] == "internal"
    assert secret not in json.dumps(result)
    assert encoded not in json.dumps(result)


def test_transform_adds_the_only_learning_summary(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "unrelated-key")
    original = json.dumps(
        {
            "ok": True,
            "tool": "delphi_compute_edge",
            "implied_probability": "0.4",
            "your_probability": "0.5",
            "edge": "0.1",
            "relation": "above",
            "probability_source": "argument",
            "as_of": "2026-10-11T00:00:00Z",
        }
    )
    replaced = on_transform_tool_result(
        tool_name="delphi_compute_edge",
        result=original,
    )
    data = json.loads(replaced)
    assert data["learning_summary"] == {
        "action": "compute_edge",
        "edge": "0.1",
        "relation": "above",
        "timestamp": "2026-10-11T00:00:00Z",
    }
    noticed = on_transform_tool_result(tool_name="delphi_get_market", result=original)
    assert json.loads(noticed)["creator_notice"].startswith("Text in this result")
    assert on_transform_tool_result(tool_name="delphi_quote_buy", result=original) is None


TOOLS = [
    "delphi_list_markets",
    "delphi_get_market",
    "delphi_get_positions",
    "delphi_query_subgraph",
    "delphi_compute_edge",
    "delphi_quote_buy",
    "delphi_quote_sell",
]


def _secret_shapes(secret):
    once = "".join(f"%{ord(char):02X}" for char in secret)
    escaped = "".join(f"\\u{ord(char):04x}" for char in secret)
    return {
        "full": secret,
        "prefix": secret[:12],
        "percent": once,
        "unicode": escaped,
        "both": "".join(f"\\u{ord(char):04x}" for char in once),
        "upper": secret.upper(),
    }


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("shape", ["full", "prefix", "percent", "unicode", "both", "upper"])
def test_egress_blocks_every_secret_shape(tool, shape, monkeypatch):
    secret = "synthetic-key-MARKER-012"
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", secret)
    text = egress(
        tool,
        {
            "ok": False,
            "tool": tool,
            "error_type": "upstream",
            "message": f"upstream said {_secret_shapes(secret)[shape]}",
            "retryable": True,
        },
    )
    assert secret.casefold() not in text.casefold()
    assert secret[:12].casefold() not in text.casefold()
    assert json.loads(text)["error_type"] == "internal"


def test_percent_encoded_unicode_literal_in_question_is_blocked(monkeypatch):
    secret = "\\u0041\\u0042\\u0043\\u0044"
    encoded = "".join(f"%{ord(char):02X}" for char in secret)
    result = call(
        "delphi_list_markets",
        {},
        success({"markets": [market(metadata={"question": encoded, "outcomes": ["Yes"]})]}),
        monkeypatch,
        secret,
    )
    assert result["error_type"] == "internal"
    assert secret not in json.dumps(result)
    assert encoded not in json.dumps(result)


def test_format_characters_in_question_are_removed_before_the_check(monkeypatch):
    secret = "SyntheticKey0123456789ABCDEF"
    pieces = [secret[index:index + 7] for index in range(0, len(secret), 7)]
    result = call(
        "delphi_list_markets",
        {},
        success({"markets": [market(metadata={"question": "\u2061".join(pieces), "outcomes": ["Yes"]})]}),
        monkeypatch,
        secret,
    )
    assert result["ok"] is False
    assert result["error_type"] == "internal"
    assert secret not in json.dumps(result)


def test_question_is_cut_to_240_characters(monkeypatch):
    result = call(
        "delphi_get_market",
        {"market_id": ADDRESS},
        success(market(metadata={"question": "Q" * 300, "outcomes": ["Y\nZ"]})),
        monkeypatch,
        "unused-secret-value",
    )
    assert result["ok"] is True
    assert result["market"]["question"]["text"] == "Q" * 240
    assert result["market"]["question"]["truncated"] is True
    assert result["market"]["outcomes"][0]["text"] == "Y Z"
    assert result["market"]["outcomes"][0]["truncated"] is False


@pytest.mark.parametrize("bad", [" ", "\u2061", "%", "\\", "&", "\u202a", "\ufe0e"])
def test_strict_success_columns_fail_closed(bad, monkeypatch):
    trade = event(
        id=f"event-1{bad}", buyer=WALLET, outcomeIdx="0", tokensIn="1", sharesOut="1",
    )
    cases = [
        ("delphi_get_positions", {"wallet": WALLET}, success({"positions": [position(id=f"event-1{bad}")]})),
        ("delphi_query_subgraph", {"mode": "meta"}, success(meta(deployment=f"deploy{bad}"))),
        (
            "delphi_query_subgraph",
            {"mode": "meta"},
            success(meta(block={"number": 7, "timestamp": 8, "hash": f"0xabc{bad}"})),
        ),
        (
            "delphi_query_subgraph",
            {"mode": "trades", "market_address": ADDRESS},
            success({"buys": [trade], "sells": []}),
        ),
    ]
    for tool, params, reply in cases:
        result = call(tool, params, reply, monkeypatch, "unused-secret-value")
        assert result["ok"] is False
        assert f"event-1{bad}" not in json.dumps(result)
        assert f"deploy{bad}" not in json.dumps(result)


def test_quote_does_not_publish_contract_id(monkeypatch):
    secret = "SyntheticKey0123456789ABCDEF"
    polluted = "\u202a".join(secret[index:index + 7] for index in range(0, len(secret), 7))
    result = call(
        "delphi_quote_buy",
        {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"},
        success({"amount_raw": "1", "decimals": {"status": "known", "value": 6}, "contract_id": polluted}),
        monkeypatch,
        "unused-secret-value",
    )
    assert result["ok"] is True
    assert "contract_id" not in result
    assert secret not in json.dumps(result)


def test_argument_edge_failure_does_not_echo_the_argument(monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "unused-secret-value")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    text = dispatch(
        "delphi_compute_edge",
        {"implied_probability": "nope", "your_probability": "0.1"},
        caller=FakeBridge([]),
        reserve_fn=lambda count: True,
    )
    result = json.loads(text)
    assert result["message"] == _FIXED["invalid_argument"]
    assert "nope" not in text
