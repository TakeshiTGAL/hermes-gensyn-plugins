"""One keyless testnet quote through the tool entry. Skip when offline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from service import dispatch

SUBGRAPH = (
    "https://api.goldsky.com/api/public/project_cmnoqdag1obop01z3efnu8ssq/"
    "subgraphs/delphi-testnet-autoset/1.0.0/gn"
)
SETTLED = "0xa29c81fc97397f7036cb277e01f6bbbe371d08a5"
QUERY = "{ gatewayBuys(first: 8, orderBy: timestamp_, orderDirection: desc) { marketProxy } }"


def _buys():
    request = urllib.request.Request(
        SUBGRAPH,
        data=json.dumps({"query": QUERY}).encode(),
        headers={
            "content-type": "application/json",
            "user-agent": "hermes-gensyn-delphi-live-check",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        page = json.load(response)
    return page["data"]["gatewayBuys"]


def _quote(address):
    return json.loads(
        dispatch(
            "delphi_quote_buy",
            {"market_address": address, "outcome_idx": 0, "shares": "1"},
        )
    )


def test_testnet_quote_and_settled_market():
    try:
        buys = _buys()
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, json.JSONDecodeError) as exc:
        pytest.skip(f"testnet subgraph unavailable: {exc}")
    opened = None
    for buy in buys:
        address = str(buy.get("marketProxy", ""))
        if not address.startswith("0x") or address.lower() == SETTLED:
            continue
        try:
            body = _quote(address)
        except OSError as exc:
            pytest.skip(f"testnet quote unavailable: {exc}")
        if body.get("ok") is True and str(body.get("amount_raw", "")).isdigit():
            opened = body
            opened["market_address"] = address
            break
    if opened is None:
        pytest.skip("no open testnet market returned a quote")
    try:
        settled = _quote(SETTLED)
    except OSError as exc:
        pytest.skip(f"settled quote unavailable: {exc}")
    assert opened["amount_raw"]
    assert settled["ok"] is False
    assert settled["error_type"] == "market_not_quotable"
