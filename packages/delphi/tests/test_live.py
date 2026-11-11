"""Quote results on the public contract. No network."""
from __future__ import annotations

import json

from service import dispatch
from tests.support import ADDRESS, FakeBridge, failure, success

SETTLED = "0xa29c81fc97397f7036cb277e01f6bbbe371d08a5"
OPEN = {"market_address": ADDRESS, "outcome_idx": 0, "shares": "1"}
SETTLED_ARGS = {"market_address": SETTLED, "outcome_idx": 0, "shares": "1"}


def _quote(monkeypatch, args, reply):
    monkeypatch.setenv("DELPHI_API_ACCESS_KEY", "test-api-key")
    monkeypatch.setenv("DELPHI_NETWORK", "testnet")
    bridge = FakeBridge([reply])
    text = dispatch(
        "delphi_quote_buy", args, caller=bridge, reserve_fn=lambda count: count <= 30,
    )
    return json.loads(text), bridge


def test_quotable_amount_and_settled_market_stay_offline(monkeypatch):
    opened, bridge = _quote(
        monkeypatch,
        OPEN,
        success({"amount_raw": "1000", "decimals": {"status": "known", "value": 18}}),
    )
    assert opened["ok"] is True
    assert str(opened["amount_raw"]).isdigit()
    assert bridge.calls and bridge.calls[0][0] == "quote_buy"
    settled, settled_bridge = _quote(
        monkeypatch,
        SETTLED_ARGS,
        failure("market_not_quotable", "execution reverted", outbound=1),
    )
    assert settled["ok"] is False
    assert settled["error_type"] == "market_not_quotable"
    assert settled_bridge.calls[0][1]["market_address"] == SETTLED
