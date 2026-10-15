"""Recorded testnet markets pass the public gate."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import re

from service import NULL_PAGES, dispatch
from tests.support import ADDRESS, WALLET, failure, success

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "testnet_markets_20261013.json"
RECORDED = json.loads(FIXTURE.read_text())
DROPPED = (
    "initial_pool", "prompt_context", "data_sources", "refund",
    "market_creation_fee", "settlement_starts",
)
ROWS = [
    *RECORDED["listMarkets"]["markets"],
    RECORDED["getMarket_settled"],
    RECORDED["getMarket_open"],
]


def _call(tool, params, reply, monkeypatch):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "test-api-key")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    text = dispatch(
        tool, params, caller=lambda *args, **kwargs: reply,
        reserve_fn=lambda count: True,
    )
    return json.loads(text), text


@pytest.mark.parametrize("row", ROWS, ids=[f"{i}" for i in range(len(ROWS))])
def test_each_recorded_market_is_public(row, monkeypatch):
    result, blob = _call(
        "delphi_get_market", {"market_id": row["id"]}, success(row), monkeypatch,
    )
    market = result["market"]
    assert result["ok"] is True
    if row.get("proof"):
        assert market["proof_kind"] == "creator_free_text"
        assert market["proof_text"]["untrusted_text"] is True
    else:
        assert market["proof_kind"] == "empty"
        assert market["proof_text"] is None
    assert market["looks_like_ree_receipt"] is False
    assert market["is_ree_receipt"] is False
    assert market["sdk_error"] is False
    assert market["trading_fee"] == row["tradingFee"]
    assert market["trading_fee_percent"] == "2"
    assert isinstance(market["proof_truncated"], bool)
    for key in DROPPED:
        assert key not in blob


def test_recorded_list_page(monkeypatch):
    result, _blob = _call(
        "delphi_list_markets", {"limit": 50}, success(RECORDED["listMarkets"]), monkeypatch,
    )
    assert result["ok"] is True
    assert len(result["markets"]) == 50


def test_open_market_identifier_is_free_text(monkeypatch):
    row = RECORDED["getMarket_open"]
    result, _blob = _call(
        "delphi_get_market", {"market_id": row["id"]}, success(row), monkeypatch,
    )
    assert result["market"]["model_identifier"]["text"] == "Claude Opus 4.6"
    assert result["market"]["model_identifier"]["untrusted_text"] is True
    assert result["market"]["status"] == "open"


def test_missing_api_market_is_not_found(monkeypatch):
    result, text = _call(
        "delphi_get_market",
        {"market_id": ADDRESS},
        {**failure("not_found"), "http_status": 404},
        monkeypatch,
    )
    assert result["ok"] is False
    assert result["error_type"] == "not_found"
    assert result["retryable"] is False
    assert result["message"] == "The market is not in the API list. (404)"
    assert ADDRESS not in text


def _sdk_null_lists():
    root = FIXTURE.parents[1].parent / "node_modules" / "@gensyn-ai" / "gensyn-delphi-sdk" / "dist"
    found = set()
    for path in root.rglob("*.d.ts"):
        found.update(re.findall(r"(\w+):\s*\w+\[\]\s*\|\s*null", path.read_text()))
    return found


def test_null_page_table_matches_the_sdk():
    assert _sdk_null_lists() == set(NULL_PAGES)


@pytest.mark.parametrize("key", sorted(NULL_PAGES))
def test_sdk_null_page_is_zero_success(key, monkeypatch):
    if key == "markets":
        tool, args, public = "delphi_list_markets", {"limit": 20}, "markets"
    else:
        tool, args, public = "delphi_get_positions", {"wallet": WALLET, "limit": 50}, "positions"
    result, _blob = _call(tool, args, success({key: None}), monkeypatch)
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["upstream_null"] is True
    assert result[public] == []
    empty, _blob = _call(tool, args, success({key: []}), monkeypatch)
    assert empty["ok"] is True
    assert empty["count"] == 0
    assert empty["upstream_null"] is False


@pytest.mark.parametrize("key", sorted(NULL_PAGES))
@pytest.mark.parametrize("bad", ["x", 1])
def test_sdk_null_page_rejects_other_types(key, bad, monkeypatch):
    if key == "markets":
        tool, args = "delphi_list_markets", {"limit": 20}
    else:
        tool, args = "delphi_get_positions", {"wallet": WALLET, "limit": 50}
    result, _blob = _call(tool, args, success({key: bad}), monkeypatch)
    assert result["ok"] is False
    assert result["error_type"] == "invalid_response"


def test_recorded_positions_probe_is_zero(monkeypatch):
    result, _blob = _call(
        "delphi_get_positions",
        {"wallet": WALLET, "limit": 50},
        success(RECORDED["positions_probe"]),
        monkeypatch,
    )
    assert result["ok"] is True
    assert result["count"] == 0
    assert result["upstream_null"] is True
    assert result["positions"] == []


def test_subgraph_array_null_stays_invalid(monkeypatch):
    result, _blob = _call(
        "delphi_query_subgraph",
        {"mode": "trades", "market_address": ADDRESS, "first": 10},
        success({"buys": None, "sells": []}),
        monkeypatch,
    )
    assert result["ok"] is False
    assert result["error_type"] == "invalid_response"


@pytest.mark.skipif(not os.environ.get("DELPHI_API_ACCESS_KEY"), reason="no key")
def test_one_live_list_when_a_key_is_present(monkeypatch):
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    text = dispatch(
        "delphi_list_markets", {"limit": 1}, reserve_fn=lambda count: True,
    )
    result = json.loads(text)
    assert result["ok"] is True
    assert len(result["markets"]) == 1
